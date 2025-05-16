# QuickBooks Data Transfer Tool

A Python tool for transferring data between QuickBooks Online companies. This tool supports transferring various QuickBooks entities including chart of accounts, employees, customers, classes, vendors, and journal entries.

Feel free to contribute to the project.

## Features

- Transfer complete chart of accounts
- Transfer employees with proper mapping
- Transfer customers and their related data
- Transfer class hierarchies and structures
- Transfer vendors and maintain proper relationships
- Transfer journal entries with proper entity references
- Maintains ID mappings between source and target companies
- Handles existing entity detection and proper error handling
- Comprehensive logging for tracking transfer progress

## Prerequisites

- Python 3.8 or higher
- Poetry (Python package manager)
- QuickBooks Online Developer Account
- Access to source and target QuickBooks companies
- OAuth2 credentials from Intuit Developer
- ngrok (for local testing with production environment)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd py-quickbooks
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Install ngrok:
```bash
# macOS (using Homebrew)
brew install ngrok

# Windows (using Chocolatey)
choco install ngrok

# Or download directly from https://ngrok.com/download
```

## Configuration

1. Create a `credentials.yml` file in the project root with your QuickBooks OAuth credentials:

```yaml
client_id: "your_client_id"
client_secret: "your_client_secret"

source:  # Source company
  environment: "sandbox"  # or "production"
  redirect_uri: "your_redirect_uri"
  company_id: "source_company_id"
  refresh_token: "source_refresh_token"
  access_token: "source_access_token"

target:  # Target company
  environment: "sandbox"  # or "production"
  redirect_uri: "your_redirect_uri"
  company_id: "target_company_id"
  refresh_token: "target_refresh_token"
  access_token: "target_access_token"
```

2. Run the token generation script to get initial tokens:
```bash
poetry run python get_tokens.py
```

## Local Testing with Production Environment

When testing with the QuickBooks production environment, you need to use HTTPS for OAuth callbacks. ngrok provides a secure tunnel to your local development environment.

1. In a new terminal, start ngrok:
```bash
ngrok http 5000
```

2. Copy the HTTPS URL provided by ngrok (e.g., https://abc123.ngrok.io)

3. Update your QuickBooks app settings:
   - Log into the Intuit Developer portal
   - Go to your app's settings
   - Add the ngrok URL to your redirect URIs:
     - `https://abc123.ngrok.io/callback`

4. Update your credentials.yml:
```yaml
# Update redirect_uri with your ngrok URL
redirect_uri: "https://abc123.ngrok.io/callback"
```

5. Start your local Flask server (from get_tokens.py):
```bash
poetry run python get_tokens.py
```

**Important Notes:**
- ngrok URLs change each time you restart ngrok (unless you have a paid account)
- Update both your app settings and credentials.yml with the new URL each time
- Keep the ngrok session running during the entire testing process
- For production use, replace ngrok URL with your actual production callback URL

## Usage

1. To transfer all data between companies:
```bash
poetry run python main.py
```

2. To transfer specific entities, edit `main.py` and uncomment the relevant transfer sections:
```python
# Transfer only vendors and journal entries
vendor_transfer = VendorTransfer(credentials_file=credentials_path)
vendor_transfer.transfer_vendors()

journal_transfer = JournalEntryTransfer(credentials_file=credentials_path)
journal_transfer.transfer_journals()
```

## Transfer Order

The tool follows a specific order for transfers to maintain data integrity:

1. Chart of Accounts
2. Employees
3. Customers
4. Classes
5. Vendors
6. Journal Entries

**Important**: Maintain this order to ensure proper entity references and mappings.

## Logging

The tool provides detailed logging at different levels:
- INFO: General progress and successful operations
- WARNING: Non-critical issues that might need attention
- ERROR: Critical issues that prevent successful transfer
- DEBUG: Detailed information for troubleshooting

Logs are output to the console by default.

## Error Handling

The tool includes comprehensive error handling for:
- API rate limits
- Authentication issues
- Duplicate entities
- Missing references
- Network issues

Each error is logged with detailed information for troubleshooting.

## Known Limitations

1. Entity names must match exactly between companies
2. Some custom fields may not transfer
3. Attachments are not transferred
4. Historical transactions are not transferred
5. Bank connections are not transferred

## Troubleshooting

1. **Authentication Issues**:
   - Verify credentials in `credentials.yml`
   - Regenerate tokens using `get_tokens.py`

2. **Missing Entities**:
   - Ensure proper transfer order is followed
   - Check logs for specific error messages
   - Verify entity exists in source company

3. **API Rate Limits**:
   - Tool includes automatic retry logic
   - For large transfers, consider breaking into smaller batches

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License. FREE and OPEN SOURCE.

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

Note: Always test thoroughly in a development environment before using in production.