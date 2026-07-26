# Google Spreadsheet Structure

This document describes the layout of the **existing** Google Spreadsheet that the
user already maintains to monitor expenses (one spreadsheet per year). It is a
description of pre-existing data, **not** a requirement on the application.

The application reads from and writes to this spreadsheet and must respect its
layout. The behavioral constraints on how the application is allowed to read/write
are captured in the functional requirements (see FR-2, FR-4, FR-5, FR-17, FR-18).

Google Sheets is the single source of truth.

---

## Support sheet (merchant rules)

The Support sheet holds the merchant categorization rules. Its layout is fixed and
must not be altered by the application.

| Column | Meaning |
|---------|---------|
| A | Primary Category |
| B | Secondary Category |
| C | Merchant Substrings |

Example:

| Primary | Secondary | Merchant Substrings |
|----------|-----------|--------------------|
| Housing | Electricity | nwg, sorgenia |
| Housing | Gas | edison |
| Groceries | Groceries general | coop, conad, carrefour |

- The Merchant Substrings cell (Column C) contains a comma-separated list of substrings.
- Empty cells indicate that no merchant rule has yet been defined for that category.
- Each Primary Category occupies a fixed block of rows.
- Each Primary Category may contain **at most 10 Secondary Categories**.


---

## Ignore patterns sheet

The Ignore patterns sheet contains one column:

| Revolut |

Each non-empty row contains one ignore pattern.

---

## Monthly expense sheets (Jan … Dec)

There is one sheet per month. The sheet name corresponds to the transaction month:

| Month | Sheet |
|--------|-------|
| January | Jan |
| February | Feb |
| March | Mar |
| April | Apr |
| May | May |
| June | Jun |
| July | Jul |
| August | Aug |
| September | Sep |
| October | Oct |
| November | Nov |
| December | Dec |

Each monthly sheet contains the following columns:

| Column | Field |
|---------|-------|
| A | Expense name |
| B | Date |
| C | Amount |
| D | Primary |
| E | Secondary |

