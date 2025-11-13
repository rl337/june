#!/usr/bin/env python3
"""
Conversation Export CLI Tool - Export conversations to JSON, TXT, or PDF formats.

Usage:
    python export_conversation.py --user-id USER_ID --chat-id CHAT_ID --format json
    python export_conversation.py --user-id USER_ID --chat-id CHAT_ID --format txt --output conversation.txt
    python export_conversation.py --user-id USER_ID --chat-id CHAT_ID --format pdf --start-date 2024-01-01 --end-date 2024-12-31
"""

import argparse
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add parent directory to path to import conversation_storage
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "telegram"))

from conversation_storage import ConversationStorage

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> datetime:
    """Parse date string in ISO format."""
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        # Try just date format
        return datetime.fromisoformat(f"{date_str}T00:00:00")


def main():
    """Main entry point for conversation export CLI."""
    parser = argparse.ArgumentParser(
        description="Export conversation to JSON, TXT, or PDF format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export to JSON
  python export_conversation.py --user-id 123 --chat-id 456 --format json

  # Export to TXT with output file
  python export_conversation.py --user-id 123 --chat-id 456 --format txt --output conversation.txt

  # Export to PDF with date range
  python export_conversation.py --user-id 123 --chat-id 456 --format pdf --start-date 2024-01-01 --end-date 2024-12-31
        """
    )
    
    parser.add_argument(
        "--user-id",
        required=True,
        help="Telegram user ID"
    )
    parser.add_argument(
        "--chat-id",
        required=True,
        help="Telegram chat ID (session_id)"
    )
    parser.add_argument(
        "--format",
        choices=["json", "txt", "pdf"],
        default="json",
        help="Export format (default: json)"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: conversation_{user_id}_{chat_id}.{format})"
    )
    parser.add_argument(
        "--start-date",
        help="Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    )
    parser.add_argument(
        "--end-date",
        help="End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    )
    
    args = parser.parse_args()
    
    # Parse dates if provided
    start_date = None
    end_date = None
    
    if args.start_date:
        try:
            start_date = parse_date(args.start_date)
        except ValueError as e:
            logger.error(f"Invalid start_date format: {e}")
            sys.exit(1)
    
    if args.end_date:
        try:
            end_date = parse_date(args.end_date)
        except ValueError as e:
            logger.error(f"Invalid end_date format: {e}")
            sys.exit(1)
    
    # Determine output file
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = Path(f"conversation_{args.user_id}_{args.chat_id}.{args.format}")
    
    try:
        logger.info(f"Exporting conversation for user_id={args.user_id}, chat_id={args.chat_id} to {args.format} format...")
        
        # Export conversation
        export_data = ConversationStorage.export_conversation(
            user_id=args.user_id,
            chat_id=args.chat_id,
            format=args.format,
            start_date=start_date,
            end_date=end_date
        )
        
        # Write to file
        with open(output_file, 'wb') as f:
            f.write(export_data)
        
        logger.info(f"Conversation exported successfully to: {output_file}")
        logger.info(f"File size: {len(export_data)} bytes")
        
    except ValueError as e:
        logger.error(f"Export failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during export: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
