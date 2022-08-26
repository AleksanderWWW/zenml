#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Repository implementation."""

import os
from abc import ABCMeta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union, cast

import zenml
from zenml.config.global_config import GlobalConfiguration
from zenml.constants import (
    ENV_ZENML_ENABLE_REPO_INIT_WARNINGS,
    ENV_ZENML_REPOSITORY_PATH,
    REPOSITORY_DIRECTORY_NAME,
    handle_bool_env_var,
)
from zenml.enums import StackComponentType
from zenml.environment import Environment
from zenml.exceptions import InitializationException
from zenml.io import fileio
from zenml.logger import get_apidocs_link, get_logger
from zenml.stack import Stack, StackComponent
from zenml.utils import io_utils
from zenml.utils.analytics_utils import AnalyticsEvent, track
from zenml.utils.filesync_model import FileSyncModel
from zenml.zen_stores import BaseZenStore

if TYPE_CHECKING:
    from zenml.pipelines import BasePipeline
    from zenml.post_execution import PipelineView
    from zenml.zen_stores.models import Project

logger = get_logger(__name__)


class RepositoryConfiguration(FileSyncModel):
    """Pydantic object used for serializing repository configuration options.

    Attributes:
        active_stack_name: Optional name of the active stack.
        active_project_name: Optional name of the active project.
    """

    active_stack_name: Optional[str]
    active_project_name: Optional[str]

    class Config:
        """Pydantic configuration class."""

        # Validate attributes when assigning them. We need to set this in order
        # to have a mix of mutable and immutable attributes
        validate_assignment = True
        # Ignore extra attributes from configs of previous ZenML versions
        extra = "ignore"
        # all attributes with leading underscore are private and therefore
        # are mutable and not included in serialization
        underscore_attrs_are_private = True


class RepositoryMetaClass(ABCMeta):
    """Repository singleton metaclass.

    This metaclass is used to enforce a singleton instance of the Repository
    class with the following additional properties:

    * the singleton Repository instance is created on first access to reflect
    the global configuration and local repository configuration.
    * the Repository shouldn't be accessed from within pipeline steps (a warning
    is logged if this is attempted).
    """

    def __init__(cls, *args: Any, **kwargs: Any) -> None:
        """Initialize the Repository class.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        super().__init__(*args, **kwargs)
        cls._global_repository: Optional["Repository"] = None

    def __call__(cls, *args: Any, **kwargs: Any) -> "Repository":
        """Create or return the global Repository instance.

        If the Repository constructor is called with custom arguments,
        the singleton functionality of the metaclass is bypassed: a new
        Repository instance is created and returned immediately and without
        saving it as the global Repository singleton.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Repository: The global Repository instance.
        """
        from zenml.steps.step_environment import (
            STEP_ENVIRONMENT_NAME,
            StepEnvironment,
        )

        step_env = cast(
            StepEnvironment, Environment().get_component(STEP_ENVIRONMENT_NAME)
        )

        # `skip_repository_check` is a special kwarg that can be passed to
        # the Repository constructor to silent the message that warns users
        # about accessing external information in their steps.
        if not kwargs.pop("skip_repository_check", False):
            if step_env and step_env.cache_enabled:
                logger.warning(
                    "You are accessing repository information from a step "
                    "that has caching enabled. Future executions of this step "
                    "may be cached even though the repository information may "
                    "be different. You should take this into consideration and "
                    "adjust your step to disable caching if needed. "
                    "Alternatively, use a `StepContext` inside your step "
                    "instead, as covered here: "
                    "https://docs.zenml.io/developer-guide/advanced-usage/step-fixtures#step-contexts",
                )

        if args or kwargs:
            return cast("Repository", super().__call__(*args, **kwargs))

        if not cls._global_repository:
            cls._global_repository = cast(
                "Repository", super().__call__(*args, **kwargs)
            )

        return cls._global_repository


class Repository(metaclass=RepositoryMetaClass):
    """ZenML repository class.

    The ZenML repository manages configuration options for ZenML stacks as well
    as their components.
    """

    def __init__(
        self,
        root: Optional[Path] = None,
    ) -> None:
        """Initializes the global repository instance.

        Repository is a singleton class: only one instance can exist. Calling
        this constructor multiple times will always yield the same instance (see
        the exception below).

        The `root` argument is only meant for internal use and testing purposes.
        User code must never pass them to the constructor.
        When a custom `root` value is passed, an anonymous Repository instance
        is created and returned independently of the Repository singleton and
        that will have no effect as far as the rest of the ZenML core code is
        concerned.

        Instead of creating a new Repository instance to reflect a different
        repository root, to change the active root in the global Repository,
        call `Repository().activate_root(<new-root>)`.

        Args:
            root: (internal use) custom root directory for the repository. If
                no path is given, the repository root is determined using the
                environment variable `ZENML_REPOSITORY_PATH` (if set) and by
                recursively searching in the parent directories of the
                current working directory. Only used to initialize new
                repositories internally.
        """
        self._root: Optional[Path] = None
        self._config: Optional[RepositoryConfiguration] = None

        self._set_active_root(root)

    @classmethod
    def get_instance(cls) -> Optional["Repository"]:
        """Return the Repository singleton instance.

        Returns:
            The Repository singleton instance or None, if the Repository hasn't
            been initialized yet.
        """
        return cls._global_repository

    @classmethod
    def _reset_instance(cls, repo: Optional["Repository"] = None) -> None:
        """Reset the Repository singleton instance.

        This method is only meant for internal use and testing purposes.

        Args:
            repo: The Repository instance to set as the global singleton.
                If None, the global Repository singleton is reset to an empty
                value.
        """
        cls._global_repository = repo

    def _set_active_root(self, root: Optional[Path] = None) -> None:
        """Set the supplied path as the repository root.

        If a repository configuration is found at the given path or the
        path, it is loaded and used to initialize the repository.
        If no repository configuration is found, the global configuration is
        used instead to manage the active stack, project etc.

        Args:
            root: The path to set as the active repository root. If not set,
                the repository root is determined using the environment
                variable `ZENML_REPOSITORY_PATH` (if set) and by recursively
                searching in the parent directories of the current working
                directory.
        """
        enable_warnings = handle_bool_env_var(
            ENV_ZENML_ENABLE_REPO_INIT_WARNINGS, True
        )
        self._root = self.find_repository(root, enable_warnings=enable_warnings)

        if not self._root:
            if enable_warnings:
                logger.info("Running without an active repository root.")
        else:
            logger.debug("Using repository root %s.", self._root)
            self._config = self._load_config()

        # Sanitize the repository configuration to reflect the current
        # settings
        self._sanitize_config()

    def _config_path(self) -> Optional[str]:
        """Path to the repository configuration file.

        Returns:
            Path to the repository configuration file or None if the repository
            root has not been initialized yet.
        """
        if not self.config_directory:
            return None
        return str(self.config_directory / "config.yaml")

    def _sanitize_config(self) -> None:
        """Sanitize and save the repository configuration.

        This method is called to ensure that the repository configuration
        doesn't contain outdated information, such as an active stack or
        project that no longer exists.
        """
        if not self._config:
            return

        # As a backup for the active stack, use the default stack or the first
        # stack in the store
        backup_stack_name: Optional[str] = None
        stacks = self.zen_store.stack_configurations

        if "default" in stacks:
            backup_stack_name = "default"
        elif stacks:
            backup_stack_name = next(iter(stacks.keys()))

        # Auto-select the repository active stack
        if not self._config.active_stack_name:
            logger.warning(
                "The repository active stack is not set. Switching the "
                "repository active stack to '%s'",
                backup_stack_name,
            )
            self._config.active_stack_name = backup_stack_name

        # Ensure that the current repository active stack is still valid
        elif self._config.active_stack_name not in stacks:
            logger.warning(
                "Stack '%s' not found. Switching the repository active stack "
                "to '%s'",
                self._config.active_stack_name,
                backup_stack_name,
            )
            self._config.active_stack_name = backup_stack_name

        # Ensure that the current repository active project is still valid
        if self._config.active_project_name:
            try:
                self.zen_store.get_project(self._config.active_project_name)
            except KeyError:
                logger.warning(
                    "Project '%s' not found. Resetting the repository active "
                    "project to the default.",
                    self._config.active_project_name,
                )
                self._config.active_project_name = None

    def _load_config(self) -> Optional[RepositoryConfiguration]:
        """Loads the repository configuration from disk.

        This happens if the repository has an active root and the configuration
        file exists. If the configuration file doesn't exist, an empty
        configuration is returned.

        Returns:
            Loaded repository configuration or None if the repository does not
            have an active root.
        """
        config_path = self._config_path()
        if not config_path:
            return None

        # load the repository configuration file if it exists, otherwise use
        # an empty configuration as default
        if fileio.exists(config_path):
            logger.debug(
                f"Loading repository configuration from {config_path}."
            )
        else:
            logger.debug(
                "No repository configuration file found, creating default "
                "configuration."
            )

        return RepositoryConfiguration(config_path)

    @staticmethod
    @track(event=AnalyticsEvent.INITIALIZE_REPO)
    def initialize(
        root: Optional[Path] = None,
    ) -> None:
        """Initializes a new ZenML repository at the given path.

        Args:
            root: The root directory where the repository should be created.
                If None, the current working directory is used.

        Raises:
            InitializationException: If the root directory already contains a
                ZenML repository.
        """
        root = root or Path.cwd()
        logger.debug("Initializing new repository at path %s.", root)
        if Repository.is_repository_directory(root):
            raise InitializationException(
                f"Found existing ZenML repository at path '{root}'."
            )

        config_directory = str(root / REPOSITORY_DIRECTORY_NAME)
        io_utils.create_dir_recursive_if_not_exists(config_directory)
        # Initialize the repository configuration at the custom path
        Repository(root=root)

    @property
    def uses_local_configuration(self) -> bool:
        """Check if the repository is using a local configuration.

        Returns:
            True if the repository is using a local configuration, False otherwise.
        """
        return self._config is not None

    @property
    def zen_store(self) -> BaseZenStore:
        """Shortcut to return the global zen store.

        Returns:
            The global zen store.
        """
        return GlobalConfiguration().zen_store

    @property
    def root(self) -> Optional[Path]:
        """The root directory of this repository.

        Returns:
            The root directory of this repository, or None, if the repository
            has not been initialized.
        """
        return self._root

    @property
    def config_directory(self) -> Optional[Path]:
        """The configuration directory of this repository.

        Returns:
            The configuration directory of this repository, or None, if the
            repository doesn't have an active root.
        """
        if not self.root:
            return None
        return self.root / REPOSITORY_DIRECTORY_NAME

    def activate_root(self, root: Optional[Path] = None) -> None:
        """Set the active repository root directory.

        Args:
            root: The path to set as the active repository root. If not set,
                the repository root is determined using the environment
                variable `ZENML_REPOSITORY_PATH` (if set) and by recursively
                searching in the parent directories of the current working
                directory.
        """
        self._set_active_root(root)

    @property
    def uses_local_active_project(self) -> bool:
        """Check if the repository is using a local active project setting.

        Returns:
            True if the repository is using a local active project setting, False
            otherwise.
        """
        return (
            self._config is not None
            and self._config.active_project_name is not None
        )

    def set_active_project(self, project: Optional[str] = None) -> None:
        """Set the project for the local repository.

        If no object is passed, this will unset the active project.

        Args:
            project: The project name to set as active.
        """
        if project:
            self.zen_store.get_project(project_name=project)  # raises KeyError
        if self._config:
            self._config.active_project_name = project
        else:
            # set the active project globally only if the repository doesn't use
            # a local configuration
            GlobalConfiguration().active_project_name = project

    @property
    def active_project_name(self) -> Optional[str]:
        """The name of the active project for this repository.

        If no active project is configured locally for the repository, the
        active project in the global configuration is used instead.

        Returns:
            The name of the active project or None, if an active project name is
            set neither in the repository configuration nor in the global
            configuration.
        """
        project_name = None
        if self._config:
            project_name = self._config.active_project_name

        if not project_name:
            project_name = GlobalConfiguration().active_project_name

        if not project_name:
            logger.info(
                "No active project is configured. Run "
                "`zenml project set PROJECT_NAME` to set the active "
                "project."
            )

        return project_name

    @property
    def active_project(self) -> Optional["Project"]:
        """Get the currently active project of the local repository.

        If no active project is configured locally for the repository, the
        active project in the global configuration is used instead.

        Returns:
            The active project or None, if an active project name is
            set neither in the repository configuration nor in the global
            configuration.
        """
        project_name = self.active_project_name
        if not project_name:
            return None

        return self.zen_store.get_project(project_name)

    @property
    def stacks(self) -> List[Stack]:
        """All stacks registered in this repository.

        Returns:
            A list of all stacks registered in this repository.
        """
        return [s.to_stack() for s in self.zen_store.stacks]

    @property
    def stack_configurations(self) -> Dict[str, Dict[StackComponentType, str]]:
        """Configuration dicts for all stacks registered in this repository.

        This property is intended as a quick way to get information about the
        components of the registered stacks without loading all installed
        integrations. The contained stack configurations might be invalid if
        they were modified by hand, to ensure you get valid stacks use
        `repo.stacks()` instead.

        Modifying the contents of the returned dictionary does not actually
        register/deregister stacks, use `repo.register_stack(...)` or
        `repo.deregister_stack(...)` instead.

        Returns:
            A dictionary containing the configuration of all stacks registered
            in this repository.
        """
        return self.zen_store.stack_configurations

    @property
    def active_stack(self) -> Stack:
        """The active stack for this repository.

        If no active stack is configured locally for the repository, the active
        stack in the global configuration is used instead.

        Returns:
            The active stack for this repository.
        """
        return self.get_stack(name=self.active_stack_name)

    @property
    def active_stack_name(self) -> str:
        """The name of the active stack for this repository.

        If no active stack is configured locally for the repository, the active
        stack in the global configuration is used instead.

        Returns:
            The name of the active stack.

        Raises:
            RuntimeError: If no active stack name is set neither in the
                repository configuration nor in the global configuration.
        """
        stack_name = None
        if self._config:
            stack_name = self._config.active_stack_name

        if not stack_name:
            stack_name = GlobalConfiguration().active_stack_name

        if not stack_name:
            raise RuntimeError(
                "No active stack is configured. Run "
                "`zenml stack set STACK_NAME` to set the active stack."
            )

        return stack_name

    @property
    def uses_local_active_stack(self) -> bool:
        """Check if the repository is using a local active stack setting.

        Returns:
            True if the repository is using a local active stack setting, False
            otherwise.
        """
        return (
            self._config is not None
            and self._config.active_stack_name is not None
        )

    @track(event=AnalyticsEvent.SET_STACK)
    def activate_stack(self, name: str) -> None:
        """Activates the stack for the given name.

        Args:
            name: Name of the stack to activate.
        """
        self.zen_store.get_stack(name)  # raises KeyError
        if self._config:
            self._config.active_stack_name = name

        else:
            # set the active stack globally only if the repository doesn't use
            # a local configuration
            GlobalConfiguration().active_stack_name = name

    def get_stack(self, name: str) -> Stack:
        """Fetches a stack.

        Args:
            name: The name of the stack to fetch.

        Returns:
            The stack with the given name.
        """
        return self.zen_store.get_stack(name).to_stack()

    def register_stack(
        self, stack: Stack, decouple_stores: bool = False
    ) -> None:
        """Registers a stack and its components.

        If any of the stack's components aren't registered in the repository
        yet, this method will try to register them as well.

        Args:
            stack: The stack to register.
            decouple_stores: Flag to reset the previous associations between
                an artifact store and a metadata store.
        """
        from zenml.zen_stores.models import StackWrapper

        stack.validate(decouple_stores=decouple_stores)
        self.zen_store.register_stack(StackWrapper.from_stack(stack))

    def update_stack(
        self,
        name: str,
        stack: Stack,
        decouple_stores: bool = False,
    ) -> None:
        """Updates a stack and its components.

        Args:
            name: The original name of the stack.
            stack: The new stack to use as the updated version.
            decouple_stores: Flag to reset the previous associations between
                an artifact store and a metadata store.
        """
        from zenml.zen_stores.models import StackWrapper

        stack.validate(decouple_stores=decouple_stores)
        self.zen_store.update_stack(name, StackWrapper.from_stack(stack))
        if self.active_stack_name == name:
            self.activate_stack(stack.name)

    def deregister_stack(self, name: str) -> None:
        """Deregisters a stack.

        Args:
            name: The name of the stack to deregister.

        Raises:
            ValueError: If the stack is the currently active stack for this
                repository.
        """
        if name == self.active_stack_name:
            raise ValueError(f"Unable to deregister active stack '{name}'.")

        try:
            self.zen_store.deregister_stack(name)
            logger.info("Deregistered stack with name '%s'.", name)
        except KeyError:
            logger.warning(
                "Unable to deregister stack with name '%s': No stack  "
                "with this name could be found.",
                name,
            )

    def update_stack_component(
        self,
        name: str,
        component_type: StackComponentType,
        component: StackComponent,
    ) -> None:
        """Updates a stack component.

        Args:
            name: The original name of the stack component.
            component_type: The type of the component to update.
            component: The new component to update with.
        """
        from zenml.zen_stores.models import ComponentWrapper

        self.zen_store.update_stack_component(
            name,
            component_type,
            ComponentWrapper.from_component(component),
        )

    def get_stack_components(
        self, component_type: StackComponentType
    ) -> List[StackComponent]:
        """Fetches all registered stack components of the given type.

        Args:
            component_type: The type of the components to fetch.

        Returns:
            A list of all registered stack components of the given type.
        """
        return [
            c.to_component()
            for c in self.zen_store.get_stack_components(component_type)
        ]

    def get_stack_component(
        self, component_type: StackComponentType, name: str
    ) -> StackComponent:
        """Fetches a registered stack component.

        Args:
            component_type: The type of the component to fetch.
            name: The name of the component to fetch.

        Returns:
            The registered stack component.
        """
        logger.debug(
            "Fetching stack component of type '%s' with name '%s'.",
            component_type.value,
            name,
        )
        return self.zen_store.get_stack_component(
            name=name,
            component_type=component_type,
        ).to_component()

    def register_stack_component(
        self,
        component: StackComponent,
    ) -> None:
        """Registers a stack component.

        Args:
            component: The component to register.
        """
        from zenml.zen_stores.models import ComponentWrapper

        self.zen_store.register_stack_component(
            ComponentWrapper.from_component(component)
        )
        if component.post_registration_message:
            logger.info(component.post_registration_message)

    def deregister_stack_component(
        self, component_type: StackComponentType, name: str
    ) -> None:
        """Deregisters a stack component.

        Args:
            component_type: The type of the component to deregister.
            name: The name of the component to deregister.
        """
        try:
            self.zen_store.deregister_stack_component(component_type, name=name)
            logger.info(
                "Deregistered stack component (type: %s) with name '%s'.",
                component_type.value,
                name,
            )
        except KeyError:
            logger.warning(
                "Unable to deregister stack component (type: %s) with name "
                "'%s': No stack component with this name could be found.",
                component_type.value,
                name,
            )

    @track(event=AnalyticsEvent.GET_PIPELINES)
    def get_pipelines(
        self, stack_name: Optional[str] = None
    ) -> List["PipelineView"]:
        """Fetches post-execution pipeline views.

        Args:
            stack_name: If specified, pipelines in the metadata store of the
                given stack are returned. Otherwise, pipelines in the metadata
                store of the currently active stack are returned.

        Returns:
            A list of post-execution pipeline views.

        Raises:
            RuntimeError: If no stack name is specified and no active stack name
                is configured.
        """
        stack_name = stack_name or self.active_stack_name
        if not stack_name:
            raise RuntimeError(
                "No active stack is configured for the repository. Run "
                "`zenml stack set STACK_NAME` to update the active stack."
            )
        metadata_store = self.get_stack(stack_name).metadata_store
        return metadata_store.get_pipelines()

    @track(event=AnalyticsEvent.GET_PIPELINE)
    def get_pipeline(
        self,
        pipeline: Optional[
            Union["BasePipeline", Type["BasePipeline"], str]
        ] = None,
        stack_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional["PipelineView"]:
        """Fetches a post-execution pipeline view.

        Use it in one of these ways:
        ```python
        # Get the pipeline by name
        Repository().get_pipeline("first_pipeline")

        # Get the step by supplying the original pipeline class
        Repository().get_step(first_pipeline)

        # Get the step by supplying an instance of the original pipeline class
        Repository().get_step(first_pipeline())
        ```

        If the specified pipeline does not (yet) exist within the repository,
        `None` will be returned.

        Args:
            pipeline: Class or class instance of the pipeline
            stack_name: If specified, pipelines in the metadata store of the
                given stack are returned. Otherwise, pipelines in the metadata
                store of the currently active stack are returned.
            **kwargs: The deprecated `pipeline_name` is caught as a kwarg to
                specify the pipeline instead of using the `pipeline` argument.

        Returns:
            A post-execution pipeline view for the given name or `None` if
            it doesn't exist.

        Raises:
            RuntimeError: If no stack name is specified and no active stack name
                is configured.
        """
        if isinstance(pipeline, str):
            pipeline_name = pipeline
        elif isinstance(pipeline, zenml.pipelines.base_pipeline.BasePipeline):
            pipeline_name = pipeline.name
        elif isinstance(pipeline, type) and issubclass(
            pipeline, zenml.pipelines.base_pipeline.BasePipeline
        ):
            pipeline_name = pipeline.__name__
        elif "pipeline_name" in kwargs and isinstance(
            kwargs.get("pipeline_name"), str
        ):
            logger.warning(
                "Using 'pipeline_name' to get a pipeline from "
                "'Repository().get_pipeline()' is deprecated and "
                "will be removed in the future. Instead please "
                "use 'pipeline' to access a pipeline in your Repository based "
                "on the name of the pipeline or even the class or instance "
                "of the pipeline. Learn more in our API docs: %s",
                get_apidocs_link(
                    "repository", "zenml.repository.Repository.get_pipeline"
                ),
            )

            pipeline_name = kwargs.pop("pipeline_name")
        else:
            raise RuntimeError(
                "No pipeline specified to get from "
                "`Repository()`. Please set a `pipeline` "
                "within the `get_pipeline()` method. Learn more "
                "in our API docs: %s",
                get_apidocs_link(
                    "repository", "zenml.repository.Repository.get_pipeline"
                ),
            )

        stack_name = stack_name or self.active_stack_name
        if not stack_name:
            raise RuntimeError(
                "No active stack is configured for the repository. Run "
                "`zenml stack set STACK_NAME` to update the active stack."
            )
        metadata_store = self.get_stack(stack_name).metadata_store

        return metadata_store.get_pipeline(pipeline_name)

    @staticmethod
    def is_repository_directory(path: Path) -> bool:
        """Checks whether a ZenML repository exists at the given path.

        Args:
            path: The path to check.

        Returns:
            True if a ZenML repository exists at the given path,
            False otherwise.
        """
        config_dir = path / REPOSITORY_DIRECTORY_NAME
        return fileio.isdir(str(config_dir))

    @staticmethod
    def find_repository(
        path: Optional[Path] = None, enable_warnings: bool = False
    ) -> Optional[Path]:
        """Search for a ZenML repository directory.

        Args:
            path: Optional path to look for the repository. If no path is
                given, this function tries to find the repository using the
                environment variable `ZENML_REPOSITORY_PATH` (if set) and
                recursively searching in the parent directories of the current
                working directory.
            enable_warnings: If `True`, warnings are printed if the repository
                root cannot be found.

        Returns:
            Absolute path to a ZenML repository directory or None if no
            repository directory was found.
        """
        if not path:
            # try to get path from the environment variable
            env_var_path = os.getenv(ENV_ZENML_REPOSITORY_PATH)
            if env_var_path:
                path = Path(env_var_path)

        if path:
            # explicit path via parameter or environment variable, don't search
            # parent directories
            search_parent_directories = False
            warning_message = (
                f"Unable to find ZenML repository at path '{path}'. Make sure "
                f"to create a ZenML repository by calling `zenml init` when "
                f"specifying an explicit repository path in code or via the "
                f"environment variable '{ENV_ZENML_REPOSITORY_PATH}'."
            )
        else:
            # try to find the repo in the parent directories of the current
            # working directory
            path = Path.cwd()
            search_parent_directories = True
            warning_message = (
                f"Unable to find ZenML repository in your current working "
                f"directory ({path}) or any parent directories. If you "
                f"want to use an existing repository which is in a different "
                f"location, set the environment variable "
                f"'{ENV_ZENML_REPOSITORY_PATH}'. If you want to create a new "
                f"repository, run `zenml init`."
            )

        def _find_repo_helper(path_: Path) -> Optional[Path]:
            """Helper function to recursively search parent directories for a ZenML repository.

            Args:
                path_: The path to search.

            Returns:
                Absolute path to a ZenML repository directory or None if no
                repository directory was found.
            """
            if Repository.is_repository_directory(path_):
                return path_

            if not search_parent_directories or io_utils.is_root(str(path_)):
                return None

            return _find_repo_helper(path_.parent)

        repo_path = _find_repo_helper(path)

        if repo_path:
            return repo_path.resolve()
        if enable_warnings:
            logger.warning(warning_message)
        return None

    def get_flavor(
        self, name: str, component_type: StackComponentType
    ) -> Type[StackComponent]:
        """Fetches a registered flavor.

        Args:
            component_type: The type of the component to fetch.
            name: The name of the flavor to fetch.

        Returns:
            The registered flavor.

        Raises:
            KeyError: If no flavor exists for the given type and name.
        """
        logger.debug(
            "Fetching the flavor of type '%s' with name '%s'.",
            component_type.value,
            name,
        )

        from zenml.stack.flavor_registry import flavor_registry

        zenml_flavors = flavor_registry.get_flavors_by_type(
            component_type=component_type
        )

        try:
            # Try to find if there are any custom flavor implementations
            flavor_wrapper = self.zen_store.get_flavor_by_name_and_type(
                flavor_name=name,
                component_type=component_type,
            )

            # If there is one, check whether the same flavor exists as a default
            # flavor to give out a warning
            if name in zenml_flavors:
                logger.warning(
                    f"There is a custom implementation for the flavor "
                    f"'{name}' of a {component_type}, which is currently "
                    f"overwriting the same flavor provided by ZenML."
                )

        except KeyError:
            if name in zenml_flavors:
                flavor_wrapper = zenml_flavors[name]
            else:
                raise KeyError(
                    f"There is no flavor '{name}' for the type "
                    f"{component_type}"
                )

        return flavor_wrapper.to_flavor()
