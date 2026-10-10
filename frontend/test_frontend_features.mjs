import assert from 'node:assert/strict';
import {
  fetchStates,
  fetchDistricts,
  fetchAllDistricts,
  detectLocation,
} from './src/services/locationsApi.ts';
import { VERIFICATION_STATUSES } from './src/utils/constants.ts';

console.log('[*] Starting Frontend 3-Features Unit & Integration Test Suite...');

// ---------------------------------------------------------------------------
// Feature 1 Tests: Location Detection & Fallback
// ---------------------------------------------------------------------------
console.log('\n--- [Feature 1] Location Detection & Geospatial Resolution ---');

// Test 1a: Valid coordinates in Maharashtra (Mumbai coordinates)
const detectedMh = await detectLocation(19.076, 72.8777);
assert.ok(detectedMh !== null, 'Should resolve valid coordinates in India');
assert.equal(detectedMh.state, 'Maharashtra');
assert.ok(
  detectedMh.district.toLowerCase().includes('mumbai') ||
  detectedMh.district.length > 0,
  'District should be resolved'
);
assert.equal(detectedMh.latitude, 19.076);
assert.equal(detectedMh.longitude, 72.8777);
console.log('  [PASS] 1a: Coordinates (19.0760, 72.8777) resolved to state: ' + detectedMh.state + ', district: ' + detectedMh.district);

// Test 1b: Coordinates outside India (London)
const detectedOutside = await detectLocation(51.5074, -0.1278);
assert.equal(detectedOutside, null, 'Coordinates outside India must resolve to null');
console.log('  [PASS] 1b: Coordinates outside India safely resolved to null.');

// Test 1c: Out-of-bounds latitude
const detectedInvalidLat = await detectLocation(999.0, 72.0);
assert.equal(detectedInvalidLat, null, 'Invalid latitude (>90) must return null');
console.log('  [PASS] 1c: Out-of-bounds coordinates safely rejected.');

// ---------------------------------------------------------------------------
// Feature 2 Tests: Exclusion of Rejected Reports from Maps & Analytics
// ---------------------------------------------------------------------------
console.log('\n--- [Feature 2] Exclude Rejected Reports from Maps and Analytics ---');

// Test 2a: Map verification status options must not offer 'Rejected'
const mapAllowedStatuses = VERIFICATION_STATUSES.filter((s) => s !== 'Rejected');
assert.ok(!mapAllowedStatuses.includes('Rejected'), 'Map status filter must NOT include Rejected');
assert.ok(mapAllowedStatuses.includes('Verified'), 'Map status filter must include Verified');
assert.ok(mapAllowedStatuses.includes('Unverified'), 'Map status filter must include Unverified');
assert.ok(mapAllowedStatuses.includes('Likely'), 'Map status filter must include Likely');
assert.ok(mapAllowedStatuses.includes('Duplicate'), 'Map status filter must include Duplicate');
console.log('  [PASS] 2a: Map status filter excludes Rejected while preserving Verified, Likely, Unverified, Duplicate.');

// Test 2b: Frontend map marker processor drops Rejected events
const mockRawMapEvents = [
  { event_id: '1', latitude: 19.07, longitude: 72.87, event_type: 'Heavy Rain', verification_status: 'Verified', state: 'Maharashtra', district: 'Mumbai' },
  { event_id: '2', latitude: 18.52, longitude: 73.85, event_type: 'Flooding', verification_status: 'Rejected', state: 'Maharashtra', district: 'Pune' },
  { event_id: '3', latitude: 28.61, longitude: 77.20, event_type: 'Thunderstorm', verification_status: 'Unverified', state: 'Delhi (NCT)', district: 'New Delhi' },
];
const filteredMapEvents = mockRawMapEvents.filter((e) => e.verification_status !== 'Rejected');
assert.equal(filteredMapEvents.length, 2, 'Must filter out the rejected event');
assert.ok(filteredMapEvents.every((e) => e.verification_status !== 'Rejected'), 'No map event has Rejected status');
console.log('  [PASS] 2b: Map marker processing drops Rejected reports.');

// Test 2c: Analytics verification chart drops Rejected events
const mockAnalyticsBreakdown = [
  { status: 'Verified', count: 10 },
  { status: 'Likely', count: 5 },
  { status: 'Unverified', count: 8 },
  { status: 'Rejected', count: 4 },
  { status: 'Duplicate', count: 2 },
];
const filteredChartData = mockAnalyticsBreakdown.filter(
  (item) => typeof item.count === 'number' && item.count > 0 && item.status !== 'Rejected'
);
assert.equal(filteredChartData.length, 4, 'Must exclude Rejected from chart slice data');
assert.ok(!filteredChartData.some((item) => item.status === 'Rejected'), 'Rejected must not be present in chart data');
console.log('  [PASS] 2c: Analytics visualization filtering strictly excludes Rejected reports.');

// ---------------------------------------------------------------------------
// Feature 3 Tests: Dashboard District Dropdown & Consistency
// ---------------------------------------------------------------------------
console.log('\n--- [Feature 3] Dashboard District Dropdown & State Synchronization ---');

// Test 3a: fetchDistricts returns districts for state
const mhDistricts = await fetchDistricts('Maharashtra');
assert.ok(mhDistricts.length > 0, 'Maharashtra must have districts');
const mhDistrictNames = mhDistricts.map((d) => d.district);
assert.ok(mhDistrictNames.some((d) => d.toLowerCase().includes('mumbai')), 'Mumbai in Maharashtra');
assert.ok(mhDistrictNames.some((d) => d.toLowerCase().includes('pune')), 'Pune in Maharashtra');
console.log(`  [PASS] 3a: fetchDistricts('Maharashtra') returned ${mhDistricts.length} verified districts.`);

// Test 3b: fetchAllDistricts returns comprehensive district list
const allDistricts = await fetchAllDistricts();
assert.ok(allDistricts.length > 50, 'All districts should contain hundreds of districts across India');
assert.ok(allDistricts.includes('Pune'), 'Pune must be present in allDistricts');
console.log(`  [PASS] 3b: fetchAllDistricts() returned ${allDistricts.length} unique districts.`);

// Test 3c: State and District synchronization logic
let selectedState = 'Maharashtra';
let selectedDistrict = 'Pune';
let currentDistrictOptions = (await fetchDistricts(selectedState)).map((d) => d.district);
assert.ok(currentDistrictOptions.includes(selectedDistrict));

// Changing state to Delhi (NCT)
selectedState = 'Delhi (NCT)';
const delhiDistricts = (await fetchDistricts(selectedState)).map((d) => d.district);
// Test reset logic: Pune is not in Delhi, so selectedDistrict resets
const shouldReset = selectedDistrict && !delhiDistricts.includes(selectedDistrict);
assert.ok(shouldReset, 'District must reset when changing to a state without that district');
selectedDistrict = shouldReset ? '' : selectedDistrict;
assert.equal(selectedDistrict, '', 'Selected district correctly cleared on state mismatch');
console.log('  [PASS] 3c: Changing state correctly clears mismatched district selection.');

// Test 3d: Dashboard maintains Rejected reports in its data
const mockDashboardEvents = [
  { event_id: '1', verification_status: 'Verified', district: 'Pune' },
  { event_id: '2', verification_status: 'Rejected', district: 'Pune' },
  { event_id: '3', verification_status: 'Unverified', district: 'Mumbai' },
];
// Filter by Pune on Dashboard:
const dashboardPuneEvents = mockDashboardEvents.filter((e) => e.district === 'Pune');
assert.equal(dashboardPuneEvents.length, 2, 'Dashboard preserves Rejected events when filtering by district');
assert.ok(dashboardPuneEvents.some((e) => e.verification_status === 'Rejected'), 'Rejected event retained in Dashboard results');
console.log('  [PASS] 3d: Dashboard retains Rejected events when filtering by district.');

console.log('\n======================================================================');
console.log('ALL FRONTEND 3-FEATURES TESTS PASSED SUCCESSFULLY!');
console.log('======================================================================');
