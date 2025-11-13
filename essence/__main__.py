"""
Main entry point for essence commands.

Usage:
    poetry run -m essence <subcommand> [args...]

Examples:
    poetry run -m essence telegram-service
    poetry run -m essence tts
    poetry run -m essence stt
"""
import argparse
import importlib
import inspect
import logging
import pkgutil
import sys
from typing import Dict, Type

from essence.command import Command

logger = logging.getLogger(__name__)


def _discover_commands() -> Dict[str, Type[Command]]:
    """
    Discover all command classes in essence.commands using reflection.
    
    Returns:
        Dictionary mapping command names to command classes
    """
    commands: Dict[str, Type[Command]] = {}
    
    try:
        import essence.commands
        
        # Iterate through all modules in essence.commands
        for importer, modname, ispkg in pkgutil.iter_modules(essence.commands.__path__, essence.commands.__name__ + "."):
            if ispkg:
                continue
            
            try:
                # Import the module
                module = importlib.import_module(modname)
                
                # Find all classes in the module that are subclasses of Command
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, Command) and 
                        obj is not Command and 
                        obj.__module__ == modname):
                        # Get the command name
                        try:
                            cmd_name = obj.get_name()
                            commands[cmd_name] = obj
                            logger.debug(f"Discovered command: {cmd_name} from {modname}")
                        except Exception as e:
                            logger.warning(f"Failed to get name from command class {name} in {modname}: {e}")
                            
            except Exception as e:
                logger.warning(f"Failed to import command module {modname}: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Failed to discover commands: {e}")
    
    return commands


def setup_logging(level: str = "INFO") -> None:
    """
    Setup logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def create_parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """
    Create the main argument parser with subcommands.
    
    Returns:
        Tuple of (parser, subparsers)
    """
    # Commands will be discovered via reflection in _register_all_commands()
    
    parser = argparse.ArgumentParser(
        description="June Essence - Core service commands",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (default: INFO)"
    )
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Service command to run",
        metavar="COMMAND",
        required=True
    )
    
    # Register all commands with subparsers
    _register_all_commands(subparsers)
    
    return parser, subparsers


def get_commands() -> Dict[str, Type[Command]]:
    """
    Get the command registry, discovering commands if needed.
    
    Returns:
        Dictionary mapping command names to command classes
    """
    # Use a module-level cache to avoid re-discovering on every call
    if not hasattr(get_commands, '_cache'):
        get_commands._cache = _discover_commands()
    return get_commands._cache


def _register_all_commands(subparsers: argparse._SubParsersAction) -> None:
    """
    Register all available commands with subparsers using reflection.
    
    Args:
        subparsers: Subparsers action to add commands to
    """
    commands = get_commands()
    
    if not commands:
        logger.warning("No commands discovered. Check that command modules exist and inherit from Command.")
        return
    
    for name, command_class in commands.items():
        try:
            description = command_class.get_description()
            cmd_parser = subparsers.add_parser(name, help=description)
            command_class.add_args(cmd_parser)
            logger.debug(f"Registered command: {name}")
        except Exception as e:
            logger.error(f"Failed to register command {name}: {e}", exc_info=True)


def main() -> int:
    """
    Main entry point for essence commands.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser, subparsers = create_parser()
    
    # Parse arguments
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Get command class using reflection
    commands = get_commands()
    command_class = commands.get(args.command)
    if not command_class:
        logger.error(f"Unknown command: {args.command}")
        logger.error(f"Available commands: {', '.join(commands.keys())}")
        return 1
    
    # Create and execute command
    try:
        command = command_class(args)
        return command.execute()
    except Exception as e:
        logger.error(f"Failed to execute command {args.command}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

