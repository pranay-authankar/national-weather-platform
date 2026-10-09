import assert from 'node:assert/strict';
import axios from 'axios';
import {
  verifyReport,
  rejectReport,
  restoreReport,
  getReportAuditHistory,
  getGlobalAuditHistory,
  extractErrorMessage,
} from './src/services/moderationApi.ts';
import apiClient from './src/services/api.ts';

console.log('[*] Starting Frontend Moderation Service Layer Unit & Integration Tests...');

// ---------------------------------------------------------------------------
// Test 1: In-Memory Token Enforcement (No Network Call when Token Missing)
// ---------------------------------------------------------------------------
console.log('\n--- [Test 1] Missing or empty token validation ---');
await assert.rejects(
  async () => {
    await verifyReport('test-id', 'Valid justification reason', '');
  },
  {
    name: 'Error',
    message: 'Admin authentication token is required.',
  },
  'Should reject when adminToken is empty'
);

await assert.rejects(
  async () => {
    await rejectReport('test-id', 'Valid justification reason', '   ');
  },
  {
    name: 'Error',
    message: 'Admin authentication token is required.',
  },
  'Should reject when adminToken is whitespace'
);
console.log('[OK] Test 1 passed: Missing/empty admin tokens safely caught before dispatching requests.');

// ---------------------------------------------------------------------------
// Test 2: Moderation Reason Validation (Minimum 3 Non-Whitespace Characters)
// ---------------------------------------------------------------------------
console.log('\n--- [Test 2] Moderation reason validation ---');
await assert.rejects(
  async () => {
    await verifyReport('test-id', 'ab', 'test-token');
  },
  {
    name: 'Error',
    message: 'Moderation reason must be at least 3 characters long.',
  },
  'Should reject reason shorter than 3 characters'
);

await assert.rejects(
  async () => {
    await restoreReport('test-id', '   ', 'test-token');
  },
  {
    name: 'Error',
    message: 'Moderation reason must be at least 3 characters long.',
  },
  'Should reject reason containing only whitespace'
);
console.log('[OK] Test 2 passed: Client-side validation strictly enforces >= 3 non-whitespace reason.');

// ---------------------------------------------------------------------------
// Test 3: Safe Error Message Extraction (Zero Credential Leakage)
// ---------------------------------------------------------------------------
console.log('\n--- [Test 3] Error message extractor safety & sanitization ---');
const secretToken = 'SECRET_ADMIN_TOKEN_XYZ';

// Standard 401 unauthorized
const mockAxios401 = {
  isAxiosError: true,
  response: {
    status: 401,
    data: { detail: 'Invalid admin authentication credentials.' },
  },
};
const err401Msg = extractErrorMessage(mockAxios401);
assert.equal(err401Msg, 'Invalid admin authentication credentials.');
assert.ok(!err401Msg.includes(secretToken));

// 400 Bad Request with transition failure detail
const mockAxios400 = {
  isAxiosError: true,
  response: {
    status: 400,
    data: { detail: 'Cannot mark a duplicate record as Verified while retaining a duplicate relationship.' },
  },
};
const err400Msg = extractErrorMessage(mockAxios400);
assert.equal(err400Msg, 'Cannot mark a duplicate record as Verified while retaining a duplicate relationship.');

// 404 Not Found
const mockAxios404 = {
  isAxiosError: true,
  response: {
    status: 404,
    data: {},
  },
};
const err404Msg = extractErrorMessage(mockAxios404);
assert.equal(err404Msg, 'Weather report record not found.');

// Fallback message
const fallbackMsg = extractErrorMessage(new Error('Network offline'));
assert.equal(fallbackMsg, 'Network offline');

console.log('[OK] Test 3 passed: Error messages safely formatted with zero credential leakage.');

// ---------------------------------------------------------------------------
// Test 4: Header Attachment & Request Dispatch Contracts
// ---------------------------------------------------------------------------
console.log('\n--- [Test 4] Request dispatch & header inspection ---');
let capturedRequest = null;

// Intercept axios request via an axios mock adapter or temporary interceptor
const interceptorId = apiClient.interceptors.request.use((config) => {
  capturedRequest = config;
  // Throw fake cancel error to prevent real network dispatch during unit test
  return Promise.reject(new axios.Cancel('TEST_INTERCEPTOR_CANCEL'));
});

try {
  await verifyReport('33333333-3333-3333-3333-333333333333', 'Valid verification justification', 'my-admin-key');
} catch {
  // Expected cancel error
} finally {
  apiClient.interceptors.request.eject(interceptorId);
}

assert.ok(capturedRequest !== null, 'Request interceptor should have captured the outgoing request');
assert.equal(capturedRequest.url, '/api/admin/reports/33333333-3333-3333-3333-333333333333/verify');
assert.equal(capturedRequest.method, 'post');
assert.deepEqual(capturedRequest.data, { reason: 'Valid verification justification' });
assert.equal(capturedRequest.headers['Authorization'], 'Bearer my-admin-key');
assert.equal(capturedRequest.headers['X-Admin-Token'], 'my-admin-key');

console.log('[OK] Test 4 passed: Outgoing request url, payload, Authorization header, and X-Admin-Token verified.');

// ---------------------------------------------------------------------------
// Test 5: Audit History Endpoint URL and Query Contracts
// ---------------------------------------------------------------------------
console.log('\n--- [Test 5] Audit history requests contract ---');
capturedRequest = null;
const auditInterceptorId = apiClient.interceptors.request.use((config) => {
  capturedRequest = config;
  return Promise.reject(new axios.Cancel('TEST_INTERCEPTOR_CANCEL'));
});

try {
  await getReportAuditHistory('44444444-4444-4444-4444-444444444444', 'admin-token-123');
} catch {
  // Expected cancel
}

assert.ok(capturedRequest !== null);
assert.equal(capturedRequest.url, '/api/admin/reports/44444444-4444-4444-4444-444444444444/audit-history');
assert.equal(capturedRequest.method, 'get');
assert.equal(capturedRequest.headers['Authorization'], 'Bearer admin-token-123');

// Global audit history query parameters
capturedRequest = null;
try {
  await getGlobalAuditHistory({ event_id: '55555555-5555-5555-5555-555555555555', limit: 25, offset: 50 }, 'admin-token-123');
} catch {
  // Expected cancel
}

assert.ok(capturedRequest !== null);
assert.equal(capturedRequest.url, '/api/admin/audit-history');
assert.equal(capturedRequest.params.event_id, '55555555-5555-5555-5555-555555555555');
assert.equal(capturedRequest.params.limit, 25);
assert.equal(capturedRequest.params.offset, 50);

apiClient.interceptors.request.eject(auditInterceptorId);
console.log('[OK] Test 5 passed: Audit history route and pagination parameters correctly mapped.');

console.log('\n==================================================');
console.log('ALL 5 FRONTEND MODERATION SERVICE TESTS PASSED!');
console.log('==================================================');
