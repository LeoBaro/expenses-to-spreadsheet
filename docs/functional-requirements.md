# Functional Requirements

## FR-1. Retrieve Transactions

The system shall periodically retrieve new transactions from the Open Banking provider (Enable Banking).

Only settled debit transactions representing expenses shall be processed.

Transactions already processed shall not be processed again.

---

## FR-2. Load Configuration

The application shall load its configuration from the Google Spreadsheet corresponding to the current year.

The spreadsheet identifier shall be configurable.

The application shall load into memory:

- Merchant rules from the **Support** sheet.
- Ignore patterns from the **Ignore patterns** sheet.

Primary Categories shall be read dynamically from the Support sheet. The application shall not hardcode category names.

Google Sheets is the single source of truth.

---

## FR-3. Merchant Matching

Merchant matching shall be performed against the transaction description.

Matching shall:

- ignore case;
- ignore leading and trailing spaces;
- succeed if any configured merchant substring is contained within the transaction description.

If multiple rules match, the longest matching substring shall take precedence.

---

## FR-4. Ignore Pattern Matching

Ignore patterns shall be evaluated before merchant categorization.

Matching shall:

- ignore case;
- ignore leading and trailing spaces;
- succeed if the transaction description contains any configured ignore pattern.

If a transaction matches an ignore pattern:

- it shall not be categorized;
- it shall not generate a Telegram notification;
- it shall not be written to the monthly expense sheet;
- it shall be marked as processed.

---

## FR-5. Automatic Categorization

If a merchant rule matches:

- assign the corresponding Primary Category;
- assign the corresponding Secondary Category;
- write the expense to the monthly expense sheet;
- mark the transaction as processed.

When a transaction is categorized automatically through a merchant rule, the application shall send a Telegram notification to the user.

The notification is informational only and does not require any user interaction.

The notification shall include:

- transaction amount;
- booking date;
- transaction description;
- assigned Primary Category;
- assigned Secondary Category.

---

## FR-6. Unknown Merchant Workflow

If no merchant rule matches:

1. Send a Telegram notification.
2. Display:
   - amount;
   - booking date;
   - transaction description.
3. Present two actions:
   - **Categorize**
   - **Ignore**

---

## FR-7. Categorization Workflow

If the user selects **Categorize**, the application shall:

1. Present the list of Primary Categories.
2. After the Primary Category is selected, present the corresponding Secondary Categories.
3. Generate candidate merchant substrings.
4. Ask the user which substring should become the merchant rule.
5. Update the Support sheet.
6. Refresh the cache.
7. Categorize the current transaction.
8. Write the transaction to the monthly expense sheet.
9. Mark the transaction as processed.

---

## FR-8. Ignore Workflow

If the user selects **Ignore**, the application shall:

1. Generate candidate ignore patterns.
2. Present the candidate patterns.
3. Allow the user to choose one pattern.
4. Append the selected pattern to the Ignore patterns sheet.
5. Refresh the cache.
6. Mark the current transaction as processed.

The transaction shall not be written to the monthly expense sheet.

---

## FR-9. Merchant Substring Suggestion

After the category has been selected, the application shall generate candidate merchant substrings.

The transaction description shall be split into words using spaces.

Candidate words shall be normalized by:

- converting to uppercase;
- trimming whitespace.

The application shall exclude:

- words already used by another merchant rule;
- configurable stop words.

Example:

```
PAGAMENTO CARTA STARBUCKS MILANO

↓

STARBUCKS
MILANO
```

The user shall select one candidate.

---

## FR-10. Ignore Pattern Suggestion

Ignore pattern generation shall use the same algorithm as merchant substring generation.

The application shall exclude:

- words already present in the Ignore patterns sheet;
- configurable stop words.

The user shall select one candidate.

---

## FR-11. Merchant Rule Persistence

After the user selects a merchant substring:

- locate the row corresponding to the selected Primary and Secondary Category;
- append the substring to Column C.

If Column C already contains values:

```
coop, carrefour
```

it becomes:

```
coop, carrefour, esselunga
```

Duplicate substrings shall not be inserted.

---

## FR-12. Expense Persistence

After a transaction has been categorized (automatically or manually), the application shall append a new row to the monthly expense sheet.

The sheet name shall correspond to the transaction month.

The destination sheet shall be determined from the transaction booking date.

The following values shall be written:

| Expense Sheet Column | Value |
|----------------------|-------|
| Expense name | Original transaction description |
| Date | Booking date |
| Amount | Transaction amount |
| Primary | Assigned Primary Category |
| Secondary | Assigned Secondary Category |

---

## FR-13. Processed Transaction State

The application shall guarantee idempotent processing.

Each transaction shall be uniquely identified using the identifier provided by the Open Banking provider.

Processed transaction identifiers shall be stored in a local state file.

On startup, the application shall load the state file before processing transactions.

Whenever a transaction is successfully:

- ignored; or
- written to the monthly expense sheet,

its identifier shall immediately be persisted to the state file.

Transactions whose identifier already exists in the state file shall be ignored.

The state file is an implementation detail and is not part of the business data.

---

## FR-14. Cache Refresh

The application shall maintain an in-memory cache containing:

- Primary Categories;
- Secondary Categories;
- Merchant Rules;
- Ignore Patterns.

The cache shall be rebuilt:

- on application startup;
- immediately after every successful update to the Support sheet;
- immediately after every successful update to the Ignore patterns sheet.