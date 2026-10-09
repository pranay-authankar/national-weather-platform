import assert from 'node:assert/strict';
import axios from 'axios';
import {
  extractSpeechErrorMessage,
  transcribeAudio,
} from './src/services/speechApi.ts';
import apiClient from './src/services/api.ts';

console.log('[*] Starting Frontend Speech-to-Text Service Layer Tests...');

// ---------------------------------------------------------------------------
// Test 1: extractSpeechErrorMessage Error Mapping
// ---------------------------------------------------------------------------
console.log('\n--- [Test 1] extractSpeechErrorMessage Mapping ---');

// Case 1a: Network error (no response)
const networkError = new axios.AxiosError('Network Error');
assert.equal(
  extractSpeechErrorMessage(networkError),
  'Unable to reach the server. Please check your network connection.'
);
console.log('  [PASS] 1a: Network error translated to friendly connection message.');

// Case 1b: 503 Service Unavailable (missing API key)
const error503 = new axios.AxiosError('Service Unavailable', 'ERR_BAD_RESPONSE', undefined, undefined, {
  status: 503,
  statusText: 'Service Unavailable',
  headers: {},
  config: {},
  data: {},
});
assert.equal(
  extractSpeechErrorMessage(error503),
  'Voice transcription service is not configured on the server (missing API key).'
);
console.log('  [PASS] 1b: HTTP 503 translated to missing configuration message.');

// Case 1c: 429 Rate Limit
const error429 = new axios.AxiosError('Too Many Requests', 'ERR_BAD_RESPONSE', undefined, undefined, {
  status: 429,
  statusText: 'Too Many Requests',
  headers: {},
  config: {},
  data: {},
});
assert.equal(
  extractSpeechErrorMessage(error429),
  'Voice transcription rate limit reached. Please wait a moment before trying again.'
);
console.log('  [PASS] 1c: HTTP 429 translated to rate limit message.');

// Case 1d: Custom detail message in response body
const customDetailError = new axios.AxiosError('Bad Request', 'ERR_BAD_REQUEST', undefined, undefined, {
  status: 400,
  statusText: 'Bad Request',
  headers: {},
  config: {},
  data: { detail: 'Audio length must be at least 100ms.' },
});
assert.equal(
  extractSpeechErrorMessage(customDetailError),
  'Audio length must be at least 100ms.'
);
console.log('  [PASS] 1d: Custom server detail propagated to user.');

// Case 1e: Standard Error instance
const standardError = new Error('Microphone permission denied');
assert.equal(
  extractSpeechErrorMessage(standardError),
  'Microphone permission denied'
);
console.log('  [PASS] 1e: Standard Error message extracted.');

// ---------------------------------------------------------------------------
// Test 2: transcribeAudio Payload & API Integration (Mocked Adapter)
// ---------------------------------------------------------------------------
console.log('\n--- [Test 2] transcribeAudio Payload Dispatch ---');

// Mock apiClient.post
const originalPost = apiClient.post;

try {
  let capturedUrl = '';
  let capturedFormData = null;
  let capturedHeaders = null;

  apiClient.post = async (url, data, config) => {
    capturedUrl = url;
    capturedFormData = data;
    capturedHeaders = config?.headers;
    return {
      status: 200,
      data: {
        text: 'Thunderstorm with heavy winds in suburban area',
        language_code: 'en',
      },
    };
  };

  // Mock audio Blob
  const mockBlob = new Blob(['mock audio binary bytes'], { type: 'audio/webm' });
  const result = await transcribeAudio(mockBlob, 'hi');

  assert.equal(capturedUrl, '/api/speech/transcribe');
  assert.equal(capturedHeaders['Content-Type'], 'multipart/form-data');
  assert.equal(result.text, 'Thunderstorm with heavy winds in suburban area');
  assert.equal(result.languageCode, 'en');

  // Verify FormData parameters
  assert.ok(capturedFormData.has('file'), 'FormData must contain "file"');
  assert.equal(capturedFormData.get('language_code'), 'hi');
  console.log('  [PASS] 2a: Audio blob and explicit language_code passed correctly.');

  // Test with 'auto' language - should NOT pass explicit language_code
  await transcribeAudio(mockBlob, 'auto');
  assert.equal(capturedFormData.has('language_code'), false, "'auto' should not append language_code param");
  console.log('  [PASS] 2b: "auto" language code correctly omitted for automatic detection.');

} finally {
  apiClient.post = originalPost;
}

console.log('\n======================================================================');
console.log('ALL FRONTEND SPEECH SERVICE TESTS COMPLETED SUCCESSFULLY!');
console.log('======================================================================\n');
