# OAuth State Lookup - Testing Instructions

## Quick Start

The OAuth callback is reaching FastAPI with both `code` and `state` present, but the state lookup is failing. 

I've added comprehensive diagnostics to identify the exact root cause.

## Testing Steps

### 1. Start the Services

```bash
# Terminal 1: Start FastAPI
python src/main.py
```

```bash
# Terminal 2: Start Telegram Bot  
python -m src.telegram_bot
```

### 2. Trigger OAuth Flow

1. Open Telegram and send `/start` to your bot
2. Click the "Connect Swiggy" button
3. Complete the Swiggy OAuth flow
4. Observe the logs in both terminals

### 3. Analyze the Logs

Look for these log sections in order:

#### A. State Creation (Telegram bot logs)
```
OAuth state CREATED:
  hash=abc123456789
  length=43
  telegram_id=123456789
  engine_url=sqlite:///...
  created_at=...
  expires_at=...
```

#### B. Authorization URL (Telegram bot logs)
```
OAuth authorize URL generated:
  authorize_state_hash=abc123456789
  authorize_state_length=43
```

**CHECK**: Does `authorize_state_hash` == `hash` from step A?
- ✅ YES → Continue
- ❌ NO → **ROOT CAUSE**: State modified during URL encoding

#### C. Callback Received (FastAPI logs)
```
OAuth callback STATE:
  callback_state_hash=abc123456789
  callback_state_length=43
  engine_url=sqlite:///...
  current_time=...
```

**CHECK**: Does `callback_state_hash` match hashes from steps A & B?
- ✅ YES → Continue
- ❌ NO → **ROOT CAUSE**: State modified by Swiggy or during redirect

#### D. Database Lookup (FastAPI logs)
```
DATABASE LOOKUP DIAGNOSTICS:
  Total OAuthState rows: 1
  engine_url=sqlite:///...
  Callback state (first/last 8 chars): '...'...'...'
  row[0]: hash=abc123456789 length=43 ...
         exact_match=True bytes_match=True
  Matching row for callback state: True
```

**CHECK 1**: Total OAuthState rows > 0?
- ✅ YES → Continue
- ❌ NO → **ROOT CAUSE**: State not committed or wrong database file

**CHECK 2**: Does row hash match callback_state_hash?
- ✅ YES → Continue  
- ❌ NO → **ROOT CAUSE**: Multiple states or wrong state selected

**CHECK 3**: `exact_match=True`?
- ✅ YES → Continue
- ❌ NO → **ROOT CAUSE**: String encoding/comparison issue

**CHECK 4**: `Matching row for callback state: True`?
- ✅ YES → Continue
- ❌ NO → **ROOT CAUSE**: SQLAlchemy query issue

#### E. Cleanup Diagnostics (FastAPI logs)
```
CLEANUP DIAGNOSTICS:
  Expired states found: 0
  States deleted: 0
  Callback state exists BEFORE cleanup: True
  Callback state exists AFTER cleanup: True
```

**CHECK**: State still exists after cleanup?
- ✅ YES → Continue
- ❌ NO → **ROOT CAUSE**: Cleanup bug (should be fixed now)

#### F. Expiry Check (FastAPI logs)
```
OAuth state check:
  created_at: ...
  expires_at (raw): ... (tzinfo: None)
  expires_at (aware): ...
  now (UTC): ...
  remaining seconds: 810.0
  is_expired: False
```

**CHECK**: `is_expired=False` and `remaining seconds > 0`?
- ✅ YES → SUCCESS! Token exchange should proceed
- ❌ NO → **ROOT CAUSE**: Timeout or clock skew

#### G. Failure Logs (if any)

If you see either of these error logs, note which one:

```
OAuth state validation FAILED: State not found in database
  Searched for state hash: ...
  State exists after cleanup: ...
```

OR

```
OAuth state validation FAILED: State expired
  State hash: ...
  Expired by: ... seconds
```

## Common Root Causes

### 1. Database Path Mismatch
**Symptom**: `engine_url` differs between creation and callback
**Solution**: Ensure both processes use same `DATABASE_URL` environment variable

### 2. State Not Committed
**Symptom**: `Total OAuthState rows: 0` during callback
**Solution**: Already fixed - `session.commit()` is called before redirect

### 3. Timezone Comparison Bug
**Symptom**: Valid state marked as expired
**Solution**: Already fixed - now using naive datetime comparison

### 4. URL Encoding Issue
**Symptom**: Hashes don't match between steps
**Solution**: Check `urllib.parse.urlencode()` usage

### 5. String Encoding Issue
**Symptom**: Hashes match but `exact_match=False`
**Solution**: Check UTF-8 encoding in database

## Running Automated Tests

```bash
# Run all OAuth state flow tests
python -m pytest test/test_oauth_state_flow.py -v

# Run with detailed output
python -m pytest test/test_oauth_state_flow.py -v -s
```

All tests should pass:
- ✅ test_oauth_state_flow_exact_reproduction
- ✅ test_oauth_wrong_state
- ✅ test_oauth_expired_state
- ✅ test_oauth_state_reuse

## What to Report

Please provide:

1. **All three hashes**:
   - creation_hash (from step A)
   - authorize_hash (from step B)
   - callback_hash (from step C)

2. **Whether hashes match**: YES/NO

3. **Database lookup results**:
   - Total rows
   - exact_match value
   - bytes_match value

4. **Engine URLs**:
   - Creation engine_url
   - Callback engine_url
   - Are they the same? YES/NO

5. **Expiry check**:
   - is_expired value
   - remaining_seconds value

6. **Error message** (if any):
   - "State not found" OR "State expired"

7. **Full logs** from both Telegram bot and FastAPI (redact any actual token values)

## Cleanup

After identifying the root cause, we can:

1. Remove verbose diagnostics
2. Keep minimal production logging (with hashes only)
3. Convert useful checks into permanent safeguards

## Security Note

These diagnostics never log actual secrets. Only SHA-256 hashes (first 12 chars) and metadata are logged.
