# OAuth State Lookup Diagnostic Report

## Changes Made

### 1. Fixed Timezone Comparison Bug in api.py

**File**: `src/api.py`
**Line**: ~307
**Issue**: Comparing timezone-aware datetime with naive datetime from SQLite
**Fix**: Convert timezone-aware `now` to naive before querying expired states

```python
# BEFORE:
expired_states = session.exec(select(OAuthState).where(OAuthState.expires_at < now)).all()

# AFTER:
now_naive = now.replace(tzinfo=None)
expired_states = session.exec(select(OAuthState).where(OAuthState.expires_at < now_naive)).all()
```

### 2. Enhanced Diagnostics with SHA-256 Hashes

Added safe logging throughout the OAuth flow that never exposes actual secrets:

#### State Creation (telegram_bot.py)
Logs when OAuthState is created:
- state_hash (first 12 chars of SHA-256)
- state_length
- telegram_id
- database path
- created_at, expires_at

#### Authorization URL (telegram_bot.py)
Logs before redirect to Swiggy:
- authorize_state_hash
- authorize_state_length
- Verification that creation hash matches authorize hash

#### Callback Handler (api.py)
Logs when callback is received:
- callback_state_hash
- callback_state_length
- callback_state sample (first/last 8 chars only)
- database path
- current UTC time

#### Database Lookup (api.py)
Logs detailed diagnostic information:
- Total OAuthState rows
- For each row: hash, length, telegram_id, expires_at
- Exact string comparison result
- Byte-by-byte comparison result
- Character-level diff if lengths match but comparison fails

#### Cleanup Diagnostics (api.py)
Logs cleanup operation:
- Number of expired states found
- Number deleted
- Whether callback state existed before cleanup
- Whether callback state exists after cleanup

### 3. Added Error Logging

Added detailed error logs for failure cases:

#### State Not Found
```python
logger.error("OAuth state validation FAILED: State not found in database")
logger.error(f"  Searched for state hash: {cb_state_hash}")
logger.error(f"  State exists after cleanup: {state_exists_after}")
```

#### State Expired
```python
logger.error("OAuth state validation FAILED: State expired")
logger.error(f"  State hash: {cb_state_hash}")
logger.error(f"  Expired by: {(now_utc - expires_at_aware).total_seconds()} seconds")
```

### 4. Created Regression Test Suite

**File**: `test/test_oauth_state_flow.py`

Tests cover:

1. **Exact OAuth Flow Reproduction**
   - Creates state in DB
   - Generates authorization URL
   - Extracts state from URL
   - Simulates callback with that exact state
   - Verifies state lookup succeeds
   - Verifies SwiggyConnection creation
   - Verifies state deletion after use

2. **Wrong State Rejection**
   - Verifies that invalid state returns 400

3. **Expired State Rejection**
   - Verifies that expired state is detected and rejected

4. **State Reuse Prevention**
   - Verifies that consumed state cannot be reused

## How to Reproduce and Test

### Run the test suite:
```bash
python -m pytest test/test_oauth_state_flow.py -v
```

### Test the actual OAuth flow:
1. Start the FastAPI server with logging enabled
2. Start the Telegram bot
3. Send `/start` to the bot
4. Click "Connect Swiggy"
5. Observe logs with the following pattern:

```
OAuth state CREATED:
  hash=abc123456789
  length=43
  telegram_id=123456789
  engine_url=sqlite:///C:\...\data\swiggy.db
  created_at=2024-01-15 10:00:00+00:00
  expires_at=2024-01-15 10:15:00+00:00

OAuth authorize URL generated:
  authorize_state_hash=abc123456789
  authorize_state_length=43

[User clicks link and Swiggy redirects]

OAuth callback STATE:
  callback_state_hash=abc123456789
  callback_state_length=43
  callback_state_repr='abcd'...'wxyz' (first/last 8 chars)
  engine_url=sqlite:///C:\...\data\swiggy.db
  current_time=2024-01-15 10:01:30+00:00

DATABASE LOOKUP DIAGNOSTICS:
  Total OAuthState rows: 1
  engine_url=sqlite:///C:\...\data\swiggy.db
  Callback state (first/last 8 chars): 'abcdefgh'...'stuvwxyz'
  row[0]: hash=abc123456789 length=43 telegram_id=123456789 expires_at=2024-01-15 10:15:00
         exact_match=True bytes_match=True
  Matching row for callback state: True

OAuth state check:
  created_at: 2024-01-15 10:00:00
  expires_at (raw): 2024-01-15 10:15:00 (tzinfo: None)
  expires_at (aware): 2024-01-15 10:15:00+00:00
  now (UTC): 2024-01-15 10:01:30+00:00
  remaining seconds: 810.0
  is_expired: False
```

## What to Look For

### Scenario A: Hashes Don't Match
If creation_hash ≠ authorize_hash ≠ callback_hash:
- **Root Cause**: State is being modified during URL encoding/decoding
- **Solution**: Check URL parameter encoding in telegram_bot.py

### Scenario B: Hashes Match But Lookup Fails
If all hashes match but `exact_match=False`:
- **Root Cause**: String encoding issue (UTF-8 vs other encoding)
- **Solution**: Check character encoding in database storage/retrieval

### Scenario C: Database Path Mismatch
If creation engine_url ≠ callback engine_url:
- **Root Cause**: Different DATABASE_URL being used
- **Solution**: Ensure consistent DATABASE_URL environment variable

### Scenario D: State Deleted by Cleanup
If "Callback state exists BEFORE cleanup: True" and "AFTER cleanup: False":
- **Root Cause**: Cleanup deleting valid state (bug in cleanup logic)
- **Solution**: Already fixed - cleanup now skips current oauth_state

### Scenario E: State Expired
If "is_expired: True":
- **Root Cause**: Too much time between creation and callback (>15 minutes)
- **Solution**: Either increase timeout or investigate why callback is delayed

### Scenario F: No States in Database
If "Total OAuthState rows: 0":
- **Root Cause**: State not committed before redirect, or wrong database file
- **Solution**: Verify session.commit() is called before building auth URL

## Security Notes

All diagnostics use SHA-256 hashes (first 12 characters only) to identify states without exposing actual values. The following are NEVER logged:
- Full OAuth state value
- Authorization code
- Access token
- Refresh token
- Code verifier (PKCE)
- Telegram bot token

Only safe representations are logged:
- First 12 chars of SHA-256 hash
- String length
- First/last 8 characters (for visual inspection only)
- Database path (non-sensitive)

## Files Modified

1. `src/api.py`:
   - Fixed timezone comparison bug
   - Added comprehensive diagnostics
   - Added error logging

2. `src/telegram_bot.py`:
   - Added state creation diagnostics
   - Added authorization URL diagnostics

3. `test/test_oauth_state_flow.py` (new file):
   - Full OAuth flow regression test
   - Edge case tests (wrong state, expired, reuse)

## Next Steps

1. **Run the actual OAuth flow** with these diagnostics enabled
2. **Capture the logs** from both Telegram bot and FastAPI
3. **Compare the hashes** at each step:
   - creation_hash
   - authorize_hash
   - callback_hash
4. **Check database diagnostics**:
   - Total rows
   - exact_match result
   - bytes_match result
5. **Identify the root cause** based on which check fails

Once the root cause is identified from the logs, the diagnostics can be removed or converted to minimal production logging.
