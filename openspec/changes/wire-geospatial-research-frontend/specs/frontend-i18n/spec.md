# Spec Delta

## Purpose

Provide a reusable bilingual (Persian/Farsi and English) UI capability for frontend apps in this repository, with runtime language switching, RTL layout for Persian, locale-aware formatting and persisted preference.

## ADDED Requirements

### Requirement: Supported locales
The UI SHALL support English (`en`) and Persian/Farsi (`fa`) as first-class locales.

#### Scenario: Default locale
- **WHEN** no preference is stored
- **THEN** the UI defaults to English

#### Scenario: Stored preference
- **WHEN** a preference is stored
- **THEN** the UI boots in that locale

### Requirement: Runtime language switching
The UI SHALL allow switching locale at runtime without a full page reload, updating all visible chrome strings.

#### Scenario: Switch to Persian
- **WHEN** the user selects Persian
- **THEN** all UI chrome strings render in Persian and the layout switches to RTL

#### Scenario: Switch to English
- **WHEN** the user selects English
- **THEN** all UI chrome strings render in English and the layout switches to LTR

### Requirement: RTL layout for Persian
The UI SHALL apply `dir="rtl"` and use logical (start/end) layout properties when the locale is Persian, so panels, toolbars and maps mirror correctly.

#### Scenario: RTL applied
- **WHEN** locale is Persian
- **THEN** the document root has `dir="rtl"` and `lang="fa"`

#### Scenario: LTR applied
- **WHEN** locale is English
- **THEN** the document root has `dir="ltr"` and `lang="en"`

### Requirement: Locale-aware formatting
The UI SHALL format dates and numbers using `Intl` with the active locale.

#### Scenario: Date formatting
- **WHEN** a date is displayed
- **THEN** it is formatted according to the active locale

#### Scenario: Number formatting
- **WHEN** a number is displayed
- **THEN** it uses the active locale's digits and grouping

### Requirement: Persisted preference
The UI SHALL persist the selected locale in browser storage and sync it for SSR/initial render.

#### Scenario: Reload
- **WHEN** the user reloads the page
- **THEN** the previously selected locale is restored before first paint

### Requirement: Translation completeness
The UI SHALL fall back to English for missing keys and provide a check that every key exists in both locale dictionaries.

#### Scenario: Missing key
- **WHEN** a key is missing in the active locale
- **THEN** the English value is shown

#### Scenario: Completeness check
- **WHEN** the i18n completeness check runs
- **THEN** it fails if any key is missing in either dictionary
