
# Non-functional Requirements

## NFR-1

The application shall be implemented in Python using FastAPI.

---

## NFR-2

Google Sheets shall be the only business data repository.

No relational or NoSQL database shall be required.

---

## NFR-3

The application may persist lightweight runtime state (e.g. processed transaction identifiers) in local files required for reliable operation.

---

## NFR-4

Google Sheets shall remain the authoritative source of truth.

The in-memory cache shall only be used to improve performance.

---

## NFR-5

The application shall minimize Google Sheets API calls by serving lookups from the in-memory cache whenever possible.

---

## NFR-6

Telegram interactions should complete within a few seconds after user input.

---

## NFR-7

The application shall be deployable as a single Docker container.

---

## NFR-8

Use uv for dependencies management