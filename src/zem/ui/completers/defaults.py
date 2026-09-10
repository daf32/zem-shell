import os
import stat
from typing import Iterable, List

from prompt_toolkit.completion import CompleteEvent, Completion, PathCompleter
from prompt_toolkit.document import Document

from zem.ui.completers.base import BaseArgCompleter


def _text_ends_with_space(document: Document) -> bool:
    """Check if the text before cursor ends with a space."""
    return document.text_before_cursor.endswith(" ")


def _get_file_type_info(path: str) -> str:
    """Get file type information for display in completion."""
    try:
        expanded = os.path.expanduser(path)
        st = os.lstat(expanded)
        mode = st.st_mode
        
        if stat.S_ISDIR(mode):
            return "📁 dir"
        elif stat.S_ISLNK(mode):
            # Check if symlink target exists
            if os.path.exists(expanded):
                if os.path.isdir(expanded):
                    return "🔗 → dir"
                return "🔗 → file"
            return "🔗 broken"
        elif stat.S_ISREG(mode):
            # Show file size for regular files
            size = st.st_size
            if size < 1024:
                return f"📄 {size}B"
            elif size < 1024 * 1024:
                return f"📄 {size // 1024}K"
            else:
                return f"📄 {size // (1024 * 1024)}M"
        elif stat.S_ISCHR(mode):
            return "⚡ char"
        elif stat.S_ISBLK(mode):
            return "💾 block"
        elif stat.S_ISFIFO(mode):
            return "📨 pipe"
        elif stat.S_ISSOCK(mode):
            return "🔌 socket"
        return "❓"
    except (OSError, IOError):
        return ""


def _current_word(text: str) -> str:
    """The word under the cursor: text after the last unescaped blank."""
    i = len(text)
    while i > 0:
        if text[i - 1].isspace() and not (i >= 2 and text[i - 2] == "\\"):
            break
        i -= 1
    return text[i:]


class EnhancedPathCompleter(PathCompleter):
    """PathCompleter with file type metadata in completion display.

    prompt_toolkit's PathCompleter treats the *entire* text before the
    cursor as the path, so it only ever worked when the path was the
    whole line. This wrapper completes the current word instead, which
    is what an argument position needs.
    """

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Get path completions (for the current word) with file type info."""
        word = _current_word(document.text_before_cursor)
        sub_document = Document(word, len(word))
        for completion in super().get_completions(sub_document, complete_event):
            # start_position is relative to the cursor, so it stays valid
            # for the full document.
            path_start = len(word) + completion.start_position
            prefix = word[:path_start] if path_start >= 0 else ""
            full_path = prefix + completion.text
            
            # If it's a relative path, make it relative to cwd
            if not full_path.startswith('/') and not full_path.startswith('~'):
                full_path = os.path.join(os.getcwd(), full_path)
            
            # Get file type info
            file_info = _get_file_type_info(full_path)
            
            yield Completion(
                text=completion.text,
                start_position=completion.start_position,
                display=completion.display,
                display_meta=file_info if file_info else completion.display_meta,
                style=completion.style,
                selected_style=completion.selected_style,
            )


class DirectoryCompleter(BaseArgCompleter):
    """Completes only directory paths with metadata."""

    fallback_to_paths = False  # "no matching directory" must not offer files
    
    def __init__(self):
        self._completer = EnhancedPathCompleter(expanduser=True, only_directories=True)
    
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        """Complete directory paths."""
        complete_event = CompleteEvent(text_inserted=False, completion_requested=True)
        return self._completer.get_completions(document, complete_event)


class GitCompleter(BaseArgCompleter):
    """Git subcommand completer with descriptions."""
    
    COMMANDS = {
        "add": "Add file contents to the index",
        "bisect": "Find bug with binary search",
        "blame": "Show what revision changed each line",
        "branch": "List, create, or delete branches",
        "checkout": "Switch branches or restore files",
        "clean": "Remove untracked files",
        "clone": "Clone a repository",
        "commit": "Record changes to the repository",
        "config": "Get and set repository options",
        "diff": "Show changes between commits",
        "fetch": "Download objects from remote",
        "init": "Create an empty Git repository",
        "log": "Show commit logs",
        "merge": "Join development histories",
        "pull": "Fetch and integrate remote changes",
        "push": "Update remote refs",
        "rebase": "Reapply commits on top of another base",
        "remote": "Manage set of tracked repositories",
        "reset": "Reset current HEAD to a state",
        "show": "Show various types of objects",
        "stash": "Stash changes in a dirty working directory",
        "status": "Show the working tree status",
        "tag": "Create, list, or delete tags",
    }
    
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        """Complete git subcommands with descriptions."""
        num_args = len(parts) - 1
        
        if num_args == 0 and _text_ends_with_space(document):
            for cmd, desc in sorted(self.COMMANDS.items()):
                yield Completion(cmd, start_position=0, display_meta=desc)
        elif num_args == 1 and word_before:
            for cmd, desc in sorted(self.COMMANDS.items()):
                if cmd.startswith(word_before):
                    yield Completion(cmd, start_position=-len(word_before), display_meta=desc)


class PipCompleter(BaseArgCompleter):
    """Pip subcommand completer."""
    
    COMMANDS = {
        "install": "Install packages",
        "uninstall": "Uninstall packages",
        "list": "List installed packages",
        "show": "Show package information",
        "freeze": "Output installed packages in requirements format",
        "search": "Search PyPI for packages",
        "download": "Download packages",
        "wheel": "Build wheels from requirements",
        "hash": "Compute hashes of package archives",
        "check": "Verify installed packages have compatible dependencies",
        "config": "Manage local and global configuration",
        "cache": "Inspect and manage pip's cache",
        "index": "Inspect information available from package indexes",
        "debug": "Show debugging information",
    }
    
    INSTALL_FLAGS = {
        "-r": "Install from requirements file",
        "--upgrade": "Upgrade package to newest version",
        "-U": "Upgrade package (short)",
        "--user": "Install to user site-packages",
        "-e": "Install package in editable mode",
        "--no-deps": "Don't install package dependencies",
        "--pre": "Include pre-release versions",
        "--force-reinstall": "Reinstall all packages",
    }
    
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        num_args = len(parts) - 1
        ends_with_space = _text_ends_with_space(document)
        
        # Complete subcommand
        if num_args == 0 and ends_with_space:
            for cmd, desc in sorted(self.COMMANDS.items()):
                yield Completion(cmd, start_position=0, display_meta=desc)
        elif num_args == 1 and word_before and not ends_with_space:
            for cmd, desc in sorted(self.COMMANDS.items()):
                if cmd.startswith(word_before):
                    yield Completion(cmd, start_position=-len(word_before), display_meta=desc)
        
        # Complete install flags
        elif num_args >= 1 and parts[1] == "install":
            if word_before.startswith("-"):
                for flag, desc in sorted(self.INSTALL_FLAGS.items()):
                    if flag.startswith(word_before):
                        yield Completion(flag, start_position=-len(word_before), display_meta=desc)


class DockerCompleter(BaseArgCompleter):
    """Docker subcommand completer."""
    
    COMMANDS = {
        "build": "Build an image from a Dockerfile",
        "run": "Run a command in a new container",
        "exec": "Run a command in a running container",
        "ps": "List containers",
        "images": "List images",
        "pull": "Pull an image from a registry",
        "push": "Push an image to a registry",
        "stop": "Stop running containers",
        "start": "Start stopped containers",
        "restart": "Restart containers",
        "rm": "Remove containers",
        "rmi": "Remove images",
        "logs": "Fetch container logs",
        "inspect": "Return low-level information",
        "network": "Manage networks",
        "volume": "Manage volumes",
        "compose": "Docker Compose commands",
        "system": "Manage Docker",
        "container": "Manage containers",
        "image": "Manage images",
    }
    
    RUN_FLAGS = {
        "-d": "Run container in background",
        "--detach": "Run container in background",
        "-it": "Interactive with TTY",
        "-p": "Publish container's port",
        "--publish": "Publish container's port",
        "-v": "Bind mount a volume",
        "--volume": "Bind mount a volume",
        "-e": "Set environment variable",
        "--env": "Set environment variable",
        "--name": "Assign a name to the container",
        "--rm": "Remove container after exit",
        "-w": "Working directory inside container",
        "--network": "Connect to a network",
    }
    
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        num_args = len(parts) - 1
        ends_with_space = _text_ends_with_space(document)
        
        # Complete subcommand
        if num_args == 0 and ends_with_space:
            for cmd, desc in sorted(self.COMMANDS.items()):
                yield Completion(cmd, start_position=0, display_meta=desc)
        elif num_args == 1 and word_before and not ends_with_space:
            for cmd, desc in sorted(self.COMMANDS.items()):
                if cmd.startswith(word_before):
                    yield Completion(cmd, start_position=-len(word_before), display_meta=desc)
        
        # Complete run flags
        elif num_args >= 1 and parts[1] == "run":
            if word_before.startswith("-"):
                for flag, desc in sorted(self.RUN_FLAGS.items()):
                    if flag.startswith(word_before):
                        yield Completion(flag, start_position=-len(word_before), display_meta=desc)


class NpmCompleter(BaseArgCompleter):
    """npm subcommand completer."""
    
    COMMANDS = {
        "install": "Install a package",
        "uninstall": "Remove a package",
        "update": "Update packages",
        "init": "Create a package.json file",
        "run": "Run a script from package.json",
        "start": "Start a package",
        "test": "Run tests",
        "build": "Build the package",
        "publish": "Publish a package",
        "pack": "Create a tarball from a package",
        "link": "Symlink a package folder",
        "list": "List installed packages",
        "ls": "List installed packages",
        "outdated": "Check for outdated packages",
        "audit": "Run a security audit",
        "cache": "Manipulate package cache",
        "config": "Manage npm configuration",
        "help": "Get help on npm",
        "version": "Bump package version",
        "view": "View registry info",
        "search": "Search for packages",
        "ci": "Install from package-lock.json",
        "exec": "Run a command from a package",
        "npx": "Run a command from a package",
    }
    
    INSTALL_FLAGS = {
        "-g": "Install globally",
        "--global": "Install globally",
        "-D": "Save as devDependency",
        "--save-dev": "Save as devDependency",
        "-P": "Save as production dependency",
        "--save-prod": "Save as production dependency",
        "-O": "Save as optionalDependency",
        "--save-optional": "Save as optionalDependency",
        "-E": "Save exact version",
        "--save-exact": "Save exact version",
        "--no-save": "Don't save to package.json",
        "--legacy-peer-deps": "Ignore peer dependencies",
        "--force": "Force reinstall",
    }
    
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        num_args = len(parts) - 1
        ends_with_space = _text_ends_with_space(document)
        
        # Complete subcommand
        if num_args == 0 and ends_with_space:
            for cmd, desc in sorted(self.COMMANDS.items()):
                yield Completion(cmd, start_position=0, display_meta=desc)
        elif num_args == 1 and word_before and not ends_with_space:
            for cmd, desc in sorted(self.COMMANDS.items()):
                if cmd.startswith(word_before):
                    yield Completion(cmd, start_position=-len(word_before), display_meta=desc)
        
        # Complete install flags
        elif num_args >= 1 and parts[1] in ("install", "i", "add"):
            if word_before.startswith("-"):
                for flag, desc in sorted(self.INSTALL_FLAGS.items()):
                    if flag.startswith(word_before):
                        yield Completion(flag, start_position=-len(word_before), display_meta=desc)
