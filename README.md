# Community Donation Bot

A comprehensive Telegram bot solution for managing community donations with manual verification, referral tracking, and multi-language support. Built with Python and aiogram.

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [Database Schema](#database-schema)
- [Troubleshooting](#troubleshooting)

## 🔭 Overview

The Community Donation Bot streamlines the process of collecting donations via Telegram. It implements a "promise-then-verify" workflow where users pledge an amount, receive payment details, and upload a proof of payment (screenshot). Administrators receive these proofs in real-time to approve or reject the transactions.

### Key Capabilities
- **Manual Verification Workflow**: Admins verify every donation receipt.
- **Multi-Card Management**: Admins can manage multiple payment methods (cards/wallets) and toggle their availability.
- **Referral System**: Users can invite others and track donations made through their links.
- **Multi-Language Support**: Full localization for English (EN), Russian (RU), and Ukrainian (UK).
- **User Profiles**: personalized profiles showing donation history and total contribution.

## ✨ Features

### User Features
- **Start & Onboarding**: Language selection and main menu navigation.
- **Make a Donation**: 
  - Enter custom amount.
  - Receive active payment details.
  - Upload receipt image.
- **History**: View last 10 transactions with status (Pending, Approved, Rejected).
- **Profile**: View personal stats and generate referral links.
- **Support**: Access contact information for help.

### Admin Features
- **Dashboard**: View key metrics (Total Raised, Pending Reviews, Total Donors).
- **Transaction Management**: 
  - Receive direct messages for new claims.
  - Approve/Reject buttons with auto-notification to users.
- **Payment Methods**: Add, delete, activate, or deactivate payment cards/details.
- **Support Message**: Update the support text directly from the bot.

## 🛠 Technology Stack

- **Core**: Python 3.10+
- **Framework**: [aiogram 3.x](https://docs.aiogram.dev/) - A modern, asynchronous framework for Telegram Bot API.
- **Database**: SQLite3 - Lightweight, serverless relational database.
- **Environment**: python-dotenv - For managing configuration secrets.
- **Logging**: Python's built-in logging module.

## 🏗 System Architecture

The application follows a modular, asynchronous architecture:

1.  **Entry Point (`bot.py`)**: Initializes the Bot, Dispatcher, and Database; registers routers.
2.  **Event Loop**: `aiogram` polls Telegram servers for updates (Messages, CallbackQueries).
3.  **Routers & Handlers**: Updates are routed to specific handlers (`handlers_user.py`, `handlers_admin.py`) based on filters.
4.  **State Management**: Uses `aiogram` FSM (Finite State Machine) to handle multi-step flows (e.g., Donation process).
5.  **Data Persistence**: `database.py` manages all SQLite interactions safely using context managers.

## 📂 Project Structure

```text
donatebot/
├── bot.py                 # Application entry point
├── config.py              # Configuration loader
├── database.py            # Database connection and queries
├── handlers_admin.py      # Admin-specific logic and handlers
├── handlers_user.py       # User-facing logic and handlers
├── i18n.py                # Internationalization strings and helpers
├── keyboards.py           # Keyboard layouts (Inline & Reply)
├── states.py              # FSM State definitions
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not committed)
└── donation_bot.db        # SQLite database (auto-created)
```

### Key Modules

- **`database.py`**: Handles connection pooling and schema migrations. Contains methods like `create_transaction`, `get_stats`, and `list_cards`.
- **`i18n.py`**: Central repository for all text strings. Uses a dictionary-based approach for translations (`TRANSLATIONS`).
- **`handlers_user.py`**: Manages the user lifecycle: `/start`, language selection, donation flow, and receipt upload.
- **`handlers_admin.py`**: Protected routes for admins. Checks `ADMIN_ID` before execution.

## 🚀 Setup & Installation

### Prerequisites
- Python 3.10 or higher
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Your Telegram User ID (from [@userinfobot](https://t.me/userinfobot))

### Installation Steps

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd donatebot
    ```

2.  **Create a virtual environment** (recommended):
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment**:
    Create a `.env` file in the root directory:
    ```env
    BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
    ADMIN_ID=12345678
    ```

5.  **Run the Bot**:
    ```bash
    python bot.py
    ```

## ⚙️ Configuration

| Variable | Description | Required |
|----------|-------------|:--------:|
| `BOT_TOKEN` | API Token provided by BotFather. | Yes |
| `ADMIN_ID` | Numeric Telegram ID of the primary administrator. | Yes |

## 📖 Usage Guide

### For Users
1.  **Start**: Send `/start` to the bot.
2.  **Language**: Choose your preferred language.
3.  **Donate**: 
    - Click "Donate".
    - Enter amount (e.g., `500`).
    - Copy the card details provided.
    - Transfer the money via your banking app.
    - Send a screenshot of the receipt to the bot.
4.  **Wait**: You will receive a notification once the admin verifies your donation.

### For Admins
1.  **Access Panel**: If your ID matches `ADMIN_ID`, you will see an "Admin Panel" button in the main menu.
2.  **Manage Cards**:
    - Go to Admin Panel -> Manage Cards.
    - Click "Add Card" to input new payment details.
    - Use "Activate/Deactivate" to control which card is shown to users.
3.  **Process Donations**:
    - When a user uploads a proof, you get a message with the photo.
    - Click **Approve** to mark it as successful and notify the user.
    - Click **Reject** to decline it.

## 🗄 Database Schema

The bot automatically creates `donation_bot.db` with the following tables:

- **`users`**: Stores user info, language preference, and referrer.
- **`transactions`**: Records donations, amounts, status (`pending_proof`, `pending_approval`, `approved`, `rejected`), and proof image IDs.
- **`cards`**: Stores payment details and their active status.
- **`settings`**: Key-value store for global settings.

## 🔧 Troubleshooting

**Issue: Bot doesn't respond.**
- Check if the python process is running.
- Verify `BOT_TOKEN` in `.env`.

**Issue: "Not Authorized" when accessing Admin Panel.**
- Ensure `ADMIN_ID` in `.env` matches your Telegram ID exactly.
- Restart the bot after changing `.env`.

**Issue: Database errors.**
- If you encounter schema errors after an update, delete `donation_bot.db` (warning: data loss) to let the bot recreate it fresh, or manually migrate the SQLite file.

---
*Documentation generated for Donation Bot v1.0*
