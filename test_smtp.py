#!/usr/bin/env python3
"""
SMTP Configuration & Diagnostic Tool for HappyBirthday.

Usage:
    python3 test_smtp.py                     # Test connection & authentication
    python3 test_smtp.py user@example.com    # Test and send a verification test email
"""

import sys
from emailer import verify_smtp_config

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 and "@" in sys.argv[1] else None
    success = verify_smtp_config(send_test_email=bool(target), target_email=target)
    sys.exit(0 if success else 1)
