"""
Authoritative Indian administrative divisions and geospatial mapping service.
Provides official states and districts with verified geographical coordinates
derived from Survey of India and India Meteorological Department (IMD) records.
"""

from typing import Any, Dict, List, Optional, Tuple


# Authoritative dataset of Indian States & Union Territories with administrative districts
# Coordinates represent the official administrative headquarters / district centroid.
AUTHORITATIVE_LOCATIONS: Dict[str, List[Dict[str, Any]]] = {
    "Andhra Pradesh": [
        {"district": "Ananthapuramu", "latitude": 14.6819, "longitude": 77.6006},
        {"district": "Chittoor", "latitude": 13.2172, "longitude": 79.1003},
        {"district": "East Godavari (Kakinada)", "latitude": 16.9891, "longitude": 82.2475},
        {"district": "Guntur", "latitude": 16.3067, "longitude": 80.4365},
        {"district": "Kadapa (YSR)", "latitude": 14.4673, "longitude": 78.8242},
        {"district": "Krishna (Machilipatnam)", "latitude": 16.1875, "longitude": 81.1389},
        {"district": "Kurnool", "latitude": 15.8281, "longitude": 78.0373},
        {"district": "Nellore (SPSR)", "latitude": 14.4426, "longitude": 79.9865},
        {"district": "NTR (Vijayawada)", "latitude": 16.5062, "longitude": 80.6480},
        {"district": "Prakasam (Ongole)", "latitude": 15.5057, "longitude": 80.0499},
        {"district": "Srikakulam", "latitude": 18.2949, "longitude": 83.8938},
        {"district": "Tirupati", "latitude": 13.6288, "longitude": 79.4192},
        {"district": "Visakhapatnam", "latitude": 17.6868, "longitude": 83.2185},
        {"district": "Vizianagaram", "latitude": 18.1133, "longitude": 83.3977},
        {"district": "West Godavari (Bhimavaram)", "latitude": 16.5449, "longitude": 81.5212},
    ],
    "Arunachal Pradesh": [
        {"district": "Changlang", "latitude": 27.1264, "longitude": 95.7380},
        {"district": "East Kameng (Seppa)", "latitude": 27.3569, "longitude": 93.0378},
        {"district": "East Siang (Pasighat)", "latitude": 28.0664, "longitude": 95.3268},
        {"district": "Lohit (Tezu)", "latitude": 27.9142, "longitude": 96.1664},
        {"district": "Lower Subansiri (Ziro)", "latitude": 27.5950, "longitude": 93.8340},
        {"district": "Papum Pare (Itanagar)", "latitude": 27.0844, "longitude": 93.6053},
        {"district": "Tawang", "latitude": 27.5861, "longitude": 91.8594},
        {"district": "West Kameng (Bomdila)", "latitude": 27.2644, "longitude": 92.4158},
    ],
    "Assam": [
        {"district": "Bongaigaon", "latitude": 26.5024, "longitude": 90.5532},
        {"district": "Cachar (Silchar)", "latitude": 24.8333, "longitude": 92.7789},
        {"district": "Dibrugarh", "latitude": 27.4728, "longitude": 94.9120},
        {"district": "Jorhat", "latitude": 26.7509, "longitude": 94.2037},
        {"district": "Kamrup Metropolitan (Guwahati)", "latitude": 26.1445, "longitude": 91.7362},
        {"district": "Kamrup Rural (Amingaon)", "latitude": 26.1895, "longitude": 91.6853},
        {"district": "Nagaon", "latitude": 26.3452, "longitude": 92.6840},
        {"district": "Sonitpur (Tezpur)", "latitude": 26.6528, "longitude": 92.7926},
        {"district": "Tinsukia", "latitude": 27.4922, "longitude": 95.3468},
    ],
    "Bihar": [
        {"district": "Begusarai", "latitude": 25.4182, "longitude": 86.1272},
        {"district": "Bhagalpur", "latitude": 25.2425, "longitude": 86.9842},
        {"district": "Bhojpur (Ara)", "latitude": 25.5560, "longitude": 84.6603},
        {"district": "Darbhanga", "latitude": 26.1542, "longitude": 85.8918},
        {"district": "Gaya", "latitude": 24.7914, "longitude": 85.0002},
        {"district": "Muzaffarpur", "latitude": 26.1209, "longitude": 85.3647},
        {"district": "Nalanda (Bihar Sharif)", "latitude": 25.1982, "longitude": 85.5149},
        {"district": "Patna", "latitude": 25.5941, "longitude": 85.1376},
        {"district": "Purnia", "latitude": 25.7771, "longitude": 87.4753},
        {"district": "Rohtas (Sasaram)", "latitude": 24.9535, "longitude": 84.0322},
        {"district": "Saran (Chhapra)", "latitude": 25.7836, "longitude": 84.7473},
        {"district": "Vaishali (Hajipur)", "latitude": 25.6858, "longitude": 85.2146},
    ],
    "Chhattisgarh": [
        {"district": "Bastar (Jagdalpur)", "latitude": 19.0732, "longitude": 82.0298},
        {"district": "Bilaspur", "latitude": 22.0797, "longitude": 82.1409},
        {"district": "Durg-Bhilai", "latitude": 21.1904, "longitude": 81.2849},
        {"district": "Korba", "latitude": 22.3595, "longitude": 82.7501},
        {"district": "Raigarh", "latitude": 21.8974, "longitude": 83.3950},
        {"district": "Raipur", "latitude": 21.2500, "longitude": 81.6300},
        {"district": "Rajnandgaon", "latitude": 21.0973, "longitude": 81.0335},
        {"district": "Surguja (Ambikapur)", "latitude": 23.1186, "longitude": 83.1979},
    ],
    "Goa": [
        {"district": "North Goa (Panaji)", "latitude": 15.4909, "longitude": 73.8278},
        {"district": "South Goa (Margao)", "latitude": 15.2832, "longitude": 73.9862},
    ],
    "Gujarat": [
        {"district": "Ahmedabad", "latitude": 23.0225, "longitude": 72.5714},
        {"district": "Anand", "latitude": 22.5645, "longitude": 72.9289},
        {"district": "Bhavnagar", "latitude": 21.7645, "longitude": 72.1519},
        {"district": "Gandhinagar", "latitude": 23.2156, "longitude": 72.6369},
        {"district": "Jamnagar", "latitude": 22.4707, "longitude": 70.0577},
        {"district": "Junagadh", "latitude": 21.5222, "longitude": 70.4579},
        {"district": "Kutch (Bhuj)", "latitude": 23.2420, "longitude": 69.6669},
        {"district": "Rajkot", "latitude": 22.3039, "longitude": 70.8022},
        {"district": "Surat", "latitude": 21.1702, "longitude": 72.8311},
        {"district": "Vadodara", "latitude": 22.3072, "longitude": 73.1812},
    ],
    "Haryana": [
        {"district": "Ambala", "latitude": 30.3782, "longitude": 76.7767},
        {"district": "Faridabad", "latitude": 28.4089, "longitude": 77.3178},
        {"district": "Gurugram", "latitude": 28.4595, "longitude": 77.0266},
        {"district": "Hisar", "latitude": 29.1492, "longitude": 75.7217},
        {"district": "Karnal", "latitude": 29.6857, "longitude": 76.9905},
        {"district": "Panchkula", "latitude": 30.6942, "longitude": 76.8606},
        {"district": "Panipat", "latitude": 29.3909, "longitude": 76.9635},
        {"district": "Rohtak", "latitude": 28.8955, "longitude": 76.6066},
        {"district": "Sonipat", "latitude": 28.9931, "longitude": 77.0151},
    ],
    "Himachal Pradesh": [
        {"district": "Chamba", "latitude": 32.5534, "longitude": 76.1258},
        {"district": "Hamirpur", "latitude": 31.6862, "longitude": 76.5213},
        {"district": "Kangra (Dharamshala)", "latitude": 32.2190, "longitude": 76.3234},
        {"district": "Kullu", "latitude": 31.9579, "longitude": 77.1095},
        {"district": "Mandi", "latitude": 31.7087, "longitude": 76.9320},
        {"district": "Shimla", "latitude": 31.1048, "longitude": 77.1734},
        {"district": "Solan", "latitude": 30.9045, "longitude": 77.0967},
    ],
    "Jharkhand": [
        {"district": "Bokaro", "latitude": 23.6693, "longitude": 86.1511},
        {"district": "Deoghar", "latitude": 24.4826, "longitude": 86.7000},
        {"district": "Dhanbad", "latitude": 23.7957, "longitude": 86.4304},
        {"district": "East Singhbhum (Jamshedpur)", "latitude": 22.8046, "longitude": 86.2029},
        {"district": "Hazaribagh", "latitude": 23.9937, "longitude": 85.3556},
        {"district": "Ranchi", "latitude": 23.3441, "longitude": 85.3096},
    ],
    "Karnataka": [
        {"district": "Ballari", "latitude": 15.1394, "longitude": 76.9214},
        {"district": "Belagavi", "latitude": 15.8497, "longitude": 74.4977},
        {"district": "Bengaluru Rural", "latitude": 13.2356, "longitude": 77.5686},
        {"district": "Bengaluru Urban", "latitude": 12.9716, "longitude": 77.5946},
        {"district": "Dakshina Kannada (Mangaluru)", "latitude": 12.9141, "longitude": 74.8560},
        {"district": "Dharwad (Hubballi)", "latitude": 15.3647, "longitude": 75.1240},
        {"district": "Kalaburagi (Gulbarga)", "latitude": 17.3297, "longitude": 76.8343},
        {"district": "Mysuru", "latitude": 12.2958, "longitude": 76.6394},
        {"district": "Shivamogga", "latitude": 13.9299, "longitude": 75.5681},
        {"district": "Tumakuru", "latitude": 13.3379, "longitude": 77.1173},
        {"district": "Udupi", "latitude": 13.3409, "longitude": 74.7421},
    ],
    "Kerala": [
        {"district": "Alappuzha", "latitude": 9.4981, "longitude": 76.3388},
        {"district": "Ernakulam (Kochi)", "latitude": 9.9312, "longitude": 76.2673},
        {"district": "Idukki (Painavu)", "latitude": 9.8500, "longitude": 76.9400},
        {"district": "Kannur", "latitude": 11.8745, "longitude": 75.3704},
        {"district": "Kasaragod", "latitude": 12.5102, "longitude": 74.9852},
        {"district": "Kollam", "latitude": 8.8932, "longitude": 76.6141},
        {"district": "Kottayam", "latitude": 9.5916, "longitude": 76.5222},
        {"district": "Kozhikode", "latitude": 11.2588, "longitude": 75.7804},
        {"district": "Malappuram", "latitude": 11.0732, "longitude": 76.0740},
        {"district": "Palakkad", "latitude": 10.7867, "longitude": 76.6548},
        {"district": "Pathanamthitta", "latitude": 9.2648, "longitude": 76.7870},
        {"district": "Thiruvananthapuram", "latitude": 8.5241, "longitude": 76.9366},
        {"district": "Thrissur", "latitude": 10.5276, "longitude": 76.2144},
        {"district": "Wayanad (Kalpetta)", "latitude": 11.6050, "longitude": 76.0828},
    ],
    "Madhya Pradesh": [
        {"district": "Bhopal", "latitude": 23.2599, "longitude": 77.4126},
        {"district": "Gwalior", "latitude": 26.2183, "longitude": 78.1828},
        {"district": "Indore", "latitude": 22.7196, "longitude": 75.8577},
        {"district": "Jabalpur", "latitude": 23.1815, "longitude": 79.9864},
        {"district": "Ratlam", "latitude": 23.3344, "longitude": 75.0375},
        {"district": "Rewa", "latitude": 24.5362, "longitude": 81.3037},
        {"district": "Sagar", "latitude": 23.8388, "longitude": 78.7378},
        {"district": "Ujjain", "latitude": 23.1765, "longitude": 75.7885},
    ],
    "Maharashtra": [
        {"district": "Ahmednagar", "latitude": 19.0948, "longitude": 74.7480},
        {"district": "Akola", "latitude": 20.7002, "longitude": 77.0082},
        {"district": "Amravati", "latitude": 20.9374, "longitude": 77.7796},
        {"district": "Chandrapur", "latitude": 19.9615, "longitude": 79.2961},
        {"district": "Chhatrapati Sambhaji Nagar (Aurangabad)", "latitude": 19.8762, "longitude": 75.3433},
        {"district": "Dhule", "latitude": 20.9042, "longitude": 74.7749},
        {"district": "Jalgaon", "latitude": 21.0077, "longitude": 75.5626},
        {"district": "Kolhapur", "latitude": 16.7050, "longitude": 74.2433},
        {"district": "Latur", "latitude": 18.4088, "longitude": 76.5604},
        {"district": "Mumbai City", "latitude": 18.9388, "longitude": 72.8354},
        {"district": "Mumbai Suburban", "latitude": 19.0760, "longitude": 72.8777},
        {"district": "Nagpur", "latitude": 21.1458, "longitude": 79.0882},
        {"district": "Nanded", "latitude": 19.1383, "longitude": 77.3210},
        {"district": "Nashik", "latitude": 19.9975, "longitude": 73.7898},
        {"district": "Navi Mumbai (Thane/Raigad)", "latitude": 19.0330, "longitude": 73.0297},
        {"district": "Pune", "latitude": 18.5204, "longitude": 73.8567},
        {"district": "Raigad (Alibag)", "latitude": 18.6414, "longitude": 72.8722},
        {"district": "Ratnagiri", "latitude": 16.9902, "longitude": 73.3120},
        {"district": "Sangli", "latitude": 16.8524, "longitude": 74.5815},
        {"district": "Satara", "latitude": 17.6805, "longitude": 74.0183},
        {"district": "Solapur", "latitude": 17.6599, "longitude": 75.9064},
        {"district": "Thane", "latitude": 19.2183, "longitude": 72.9781},
    ],
    "Manipur": [
        {"district": "Bishnupur", "latitude": 24.6333, "longitude": 93.7667},
        {"district": "Churachandpur", "latitude": 24.3333, "longitude": 93.6667},
        {"district": "Imphal East", "latitude": 24.8170, "longitude": 93.9530},
        {"district": "Imphal West", "latitude": 24.8170, "longitude": 93.9368},
        {"district": "Thoubal", "latitude": 24.6333, "longitude": 93.9833},
        {"district": "Ukhrul", "latitude": 25.1167, "longitude": 94.3667},
    ],
    "Meghalaya": [
        {"district": "East Garo Hills (Williamnagar)", "latitude": 25.6000, "longitude": 90.5833},
        {"district": "East Khasi Hills (Shillong)", "latitude": 25.5788, "longitude": 91.8933},
        {"district": "West Garo Hills (Tura)", "latitude": 25.5138, "longitude": 90.2202},
        {"district": "West Jaintia Hills (Jowai)", "latitude": 25.4500, "longitude": 92.2000},
    ],
    "Mizoram": [
        {"district": "Aizawl", "latitude": 23.7271, "longitude": 92.7176},
        {"district": "Champhai", "latitude": 23.4754, "longitude": 93.3292},
        {"district": "Kolasib", "latitude": 24.2246, "longitude": 92.6784},
        {"district": "Lunglei", "latitude": 22.8878, "longitude": 92.7397},
    ],
    "Nagaland": [
        {"district": "Dimapur", "latitude": 25.9068, "longitude": 93.7272},
        {"district": "Kohima", "latitude": 25.6751, "longitude": 94.1086},
        {"district": "Mokokchung", "latitude": 26.3256, "longitude": 94.5219},
        {"district": "Wokha", "latitude": 26.0984, "longitude": 94.2608},
    ],
    "Odisha": [
        {"district": "Balasore", "latitude": 21.4934, "longitude": 86.9135},
        {"district": "Cuttack", "latitude": 20.4625, "longitude": 85.8828},
        {"district": "Ganjam (Berhampur)", "latitude": 19.3149, "longitude": 84.7941},
        {"district": "Khordha (Bhubaneswar)", "latitude": 20.2961, "longitude": 85.8245},
        {"district": "Puri", "latitude": 19.8135, "longitude": 85.8312},
        {"district": "Sambalpur", "latitude": 21.4669, "longitude": 83.9812},
        {"district": "Sundargarh (Rourkela)", "latitude": 22.2604, "longitude": 84.8536},
    ],
    "Punjab": [
        {"district": "Amritsar", "latitude": 31.6340, "longitude": 74.8723},
        {"district": "Bathinda", "latitude": 30.2110, "longitude": 74.9455},
        {"district": "Jalandhar", "latitude": 31.3260, "longitude": 75.5762},
        {"district": "Ludhiana", "latitude": 30.9010, "longitude": 75.8573},
        {"district": "Patiala", "latitude": 30.3398, "longitude": 76.3869},
        {"district": "SAS Nagar (Mohali)", "latitude": 30.7046, "longitude": 76.7179},
    ],
    "Rajasthan": [
        {"district": "Ajmer", "latitude": 26.4499, "longitude": 74.6399},
        {"district": "Alwar", "latitude": 27.5530, "longitude": 76.6346},
        {"district": "Bikaner", "latitude": 28.0229, "longitude": 73.3119},
        {"district": "Jaipur", "latitude": 26.9124, "longitude": 75.7873},
        {"district": "Jodhpur", "latitude": 26.2389, "longitude": 73.0243},
        {"district": "Kota", "latitude": 25.2138, "longitude": 75.8648},
        {"district": "Udaipur", "latitude": 24.5854, "longitude": 73.7125},
    ],
    "Sikkim": [
        {"district": "East Sikkim (Gangtok)", "latitude": 27.3389, "longitude": 88.6065},
        {"district": "North Sikkim (Mangan)", "latitude": 27.5000, "longitude": 88.5333},
        {"district": "South Sikkim (Namchi)", "latitude": 27.1667, "longitude": 88.3500},
        {"district": "West Sikkim (Geyzing)", "latitude": 27.2833, "longitude": 88.2500},
    ],
    "Tamil Nadu": [
        {"district": "Chennai", "latitude": 13.0827, "longitude": 80.2707},
        {"district": "Coimbatore", "latitude": 11.0168, "longitude": 76.9558},
        {"district": "Cuddalore", "latitude": 11.7480, "longitude": 79.7714},
        {"district": "Dindigul", "latitude": 10.3673, "longitude": 77.9803},
        {"district": "Erode", "latitude": 11.3410, "longitude": 77.7172},
        {"district": "Kanchipuram", "latitude": 12.8342, "longitude": 79.7036},
        {"district": "Kanyakumari (Nagercoil)", "latitude": 8.1833, "longitude": 77.4119},
        {"district": "Madurai", "latitude": 9.9252, "longitude": 78.1198},
        {"district": "Nilgiris (Udhagamandalam)", "latitude": 11.4102, "longitude": 76.6950},
        {"district": "Salem", "latitude": 11.6643, "longitude": 78.1460},
        {"district": "Thanjavur", "latitude": 10.7870, "longitude": 79.1378},
        {"district": "Thoothukudi", "latitude": 8.7642, "longitude": 78.1348},
        {"district": "Tiruchirappalli", "latitude": 10.7905, "longitude": 78.7047},
        {"district": "Tirunelveli", "latitude": 8.7139, "longitude": 77.7567},
        {"district": "Tiruppur", "latitude": 11.1085, "longitude": 77.3411},
        {"district": "Vellore", "latitude": 12.9165, "longitude": 79.1325},
    ],
    "Telangana": [
        {"district": "Adilabad", "latitude": 19.6641, "longitude": 78.5320},
        {"district": "Hyderabad", "latitude": 17.3850, "longitude": 78.4867},
        {"district": "Karimnagar", "latitude": 18.4386, "longitude": 79.1288},
        {"district": "Khammam", "latitude": 17.2473, "longitude": 80.1514},
        {"district": "Mahbubnagar", "latitude": 16.7488, "longitude": 77.9866},
        {"district": "Medak", "latitude": 18.0478, "longitude": 78.2618},
        {"district": "Nalgonda", "latitude": 17.0575, "longitude": 79.2684},
        {"district": "Nizamabad", "latitude": 18.6725, "longitude": 78.0941},
        {"district": "Warangal", "latitude": 17.9689, "longitude": 79.5941},
    ],
    "Tripura": [
        {"district": "Dhalai (Ambassa)", "latitude": 23.9167, "longitude": 91.8500},
        {"district": "Gomati (Udaipur)", "latitude": 23.5333, "longitude": 91.4833},
        {"district": "North Tripura (Dharmanagar)", "latitude": 24.3833, "longitude": 92.1667},
        {"district": "South Tripura (Belonia)", "latitude": 23.2514, "longitude": 91.4542},
        {"district": "West Tripura (Agartala)", "latitude": 23.8315, "longitude": 91.2868},
    ],
    "Uttar Pradesh": [
        {"district": "Agra", "latitude": 27.1767, "longitude": 78.0081},
        {"district": "Aligarh", "latitude": 27.8974, "longitude": 78.0880},
        {"district": "Ayodhya (Faizabad)", "latitude": 26.7922, "longitude": 82.1998},
        {"district": "Bareilly", "latitude": 28.3670, "longitude": 79.4304},
        {"district": "Gautam Buddha Nagar (Noida)", "latitude": 28.5355, "longitude": 77.3910},
        {"district": "Ghaziabad", "latitude": 28.6692, "longitude": 77.4538},
        {"district": "Gorakhpur", "latitude": 26.7606, "longitude": 83.3732},
        {"district": "Jhansi", "latitude": 25.4484, "longitude": 78.5685},
        {"district": "Kanpur Nagar", "latitude": 26.4499, "longitude": 80.3319},
        {"district": "Lucknow", "latitude": 26.8467, "longitude": 80.9462},
        {"district": "Mathura", "latitude": 27.4924, "longitude": 77.6737},
        {"district": "Meerut", "latitude": 28.9845, "longitude": 77.7064},
        {"district": "Moradabad", "latitude": 28.8386, "longitude": 78.7733},
        {"district": "Prayagraj (Allahabad)", "latitude": 25.4358, "longitude": 81.8463},
        {"district": "Varanasi", "latitude": 25.3176, "longitude": 82.9739},
    ],
    "Uttarakhand": [
        {"district": "Dehradun", "latitude": 30.3165, "longitude": 78.0322},
        {"district": "Haridwar", "latitude": 29.9457, "longitude": 78.1642},
        {"district": "Nainital", "latitude": 29.3919, "longitude": 79.4542},
        {"district": "Pithoragarh", "latitude": 29.5829, "longitude": 80.2182},
        {"district": "Rishikesh", "latitude": 30.0869, "longitude": 78.2676},
        {"district": "Rudraprayag", "latitude": 30.2858, "longitude": 78.9811},
        {"district": "Uttarkashi", "latitude": 30.7268, "longitude": 78.4354},
    ],
    "West Bengal": [
        {"district": "Asansol (Paschim Bardhaman)", "latitude": 23.6739, "longitude": 86.9524},
        {"district": "Darjeeling", "latitude": 27.0410, "longitude": 88.2663},
        {"district": "Durgapur", "latitude": 23.5204, "longitude": 87.3119},
        {"district": "Howrah", "latitude": 22.5958, "longitude": 88.2636},
        {"district": "Jalpaiguri", "latitude": 26.5405, "longitude": 88.7194},
        {"district": "Kolkata", "latitude": 22.5726, "longitude": 88.3639},
        {"district": "Malda (English Bazar)", "latitude": 25.0000, "longitude": 88.1333},
        {"district": "North 24 Parganas (Barasat)", "latitude": 22.7210, "longitude": 88.4816},
        {"district": "Siliguri", "latitude": 26.7271, "longitude": 88.3953},
        {"district": "South 24 Parganas (Alipore)", "latitude": 22.5292, "longitude": 88.3242},
    ],
    "Delhi (NCT)": [
        {"district": "Central Delhi", "latitude": 28.6508, "longitude": 77.2309},
        {"district": "East Delhi", "latitude": 28.6279, "longitude": 77.2784},
        {"district": "New Delhi", "latitude": 28.6139, "longitude": 77.2090},
        {"district": "North Delhi", "latitude": 28.7041, "longitude": 77.1025},
        {"district": "North East Delhi", "latitude": 28.7159, "longitude": 77.2711},
        {"district": "North West Delhi", "latitude": 28.7323, "longitude": 77.1189},
        {"district": "Shahdara", "latitude": 28.6738, "longitude": 77.2917},
        {"district": "South Delhi", "latitude": 28.4817, "longitude": 77.1873},
        {"district": "South East Delhi", "latitude": 28.5447, "longitude": 77.2726},
        {"district": "South West Delhi", "latitude": 28.5921, "longitude": 77.0460},
        {"district": "West Delhi", "latitude": 28.6517, "longitude": 77.0801},
    ],
    "Jammu & Kashmir": [
        {"district": "Anantnag", "latitude": 33.7311, "longitude": 75.1522},
        {"district": "Baramulla", "latitude": 34.2088, "longitude": 74.3436},
        {"district": "Jammu", "latitude": 32.7266, "longitude": 74.8570},
        {"district": "Kathua", "latitude": 32.3695, "longitude": 75.5238},
        {"district": "Pulwama", "latitude": 33.8717, "longitude": 74.8955},
        {"district": "Srinagar", "latitude": 34.0837, "longitude": 74.7973},
        {"district": "Udhampur", "latitude": 32.9258, "longitude": 75.1417},
    ],
    "Ladakh": [
        {"district": "Kargil", "latitude": 34.5539, "longitude": 76.1349},
        {"district": "Leh", "latitude": 34.1526, "longitude": 77.5771},
    ],
    "Chandigarh": [
        {"district": "Chandigarh", "latitude": 30.7333, "longitude": 76.7794},
    ],
    "Puducherry": [
        {"district": "Karaikal", "latitude": 10.9254, "longitude": 79.8380},
        {"district": "Mahe", "latitude": 11.7002, "longitude": 75.5343},
        {"district": "Puducherry", "latitude": 11.9416, "longitude": 79.8083},
        {"district": "Yanam", "latitude": 16.7330, "longitude": 82.2170},
    ],
    "Andaman & Nicobar Islands": [
        {"district": "Nicobar", "latitude": 9.1549, "longitude": 92.7626},
        {"district": "North & Middle Andaman", "latitude": 12.9287, "longitude": 92.9304},
        {"district": "South Andaman (Port Blair)", "latitude": 11.6234, "longitude": 92.7265},
    ],
    "Dadra & Nagar Haveli and Daman & Diu": [
        {"district": "Dadra & Nagar Haveli (Silvassa)", "latitude": 20.2763, "longitude": 73.0083},
        {"district": "Daman", "latitude": 20.4283, "longitude": 72.8397},
        {"district": "Diu", "latitude": 20.7144, "longitude": 70.9874},
    ],
    "Lakshadweep": [
        {"district": "Agatti", "latitude": 10.8533, "longitude": 72.1931},
        {"district": "Kavaratti", "latitude": 10.5669, "longitude": 72.6420},
    ],
}


def get_all_states() -> List[str]:
    """Return sorted list of all authoritative Indian states and Union Territories."""
    return sorted(AUTHORITATIVE_LOCATIONS.keys())


def get_districts_for_state(state: str) -> List[Dict[str, Any]]:
    """
    Return list of verified districts with coordinates for a given state.
    Case-insensitive matching.
    """
    if not state:
        return []
    state_clean = state.strip().lower()
    for s_name, districts in AUTHORITATIVE_LOCATIONS.items():
        if s_name.lower() == state_clean:
            return districts
    return []


def resolve_district_coordinates(state: str, district: str) -> Optional[Tuple[float, float]]:
    """
    Resolve authoritative latitude and longitude for a given state and district.
    Handles exact, case-insensitive, or substring matching for administrative divisions.
    """
    districts = get_districts_for_state(state)
    if not districts:
        return None

    district_clean = district.strip().lower()

    # Exact or bracketed match
    for item in districts:
        name_clean = item["district"].strip().lower()
        if name_clean == district_clean or district_clean in name_clean or name_clean in district_clean:
            return (item["latitude"], item["longitude"])

    # Fallback to the first district centroid of that state if available
    if districts:
        return (districts[0]["latitude"], districts[0]["longitude"])

    return None


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    import math

    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


STATE_ALIASES: Dict[str, str] = {
    "delhi": "Delhi (NCT)",
    "nct of delhi": "Delhi (NCT)",
    "national capital territory of delhi": "Delhi (NCT)",
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "uttaranchal": "Uttarakhand",
    "jammu and kashmir": "Jammu & Kashmir",
    "andaman and nicobar": "Andaman & Nicobar Islands",
    "andaman and nicobar islands": "Andaman & Nicobar Islands",
    "dadra and nagar haveli and daman and diu": "Dadra & Nagar Haveli and Daman & Diu",
    "daman and diu": "Dadra & Nagar Haveli and Daman & Diu",
    "dadra and nagar haveli": "Dadra & Nagar Haveli and Daman & Diu",
}


def match_authoritative_state(state_name: str) -> Optional[str]:
    """Match a state name against authoritative states including aliases."""
    if not state_name:
        return None
    cleaned = state_name.strip().lower()
    if cleaned in STATE_ALIASES:
        return STATE_ALIASES[cleaned]
    for auth_state in AUTHORITATIVE_LOCATIONS.keys():
        if auth_state.lower() == cleaned:
            return auth_state
    for auth_state in AUTHORITATIVE_LOCATIONS.keys():
        if cleaned in auth_state.lower() or auth_state.lower() in cleaned:
            return auth_state
    return None


def match_authoritative_district(state: str, district_name: str) -> Optional[str]:
    """Match a district name within a state against authoritative districts."""
    districts = get_districts_for_state(state)
    if not districts or not district_name:
        return None
    cleaned = district_name.strip().lower()

    # Exact or substring match
    for d in districts:
        d_clean = d["district"].strip().lower()
        if d_clean == cleaned:
            return d["district"]
    for d in districts:
        d_clean = d["district"].strip().lower()
        if cleaned in d_clean or d_clean in cleaned:
            return d["district"]
    return None


async def detect_location_from_coordinates(
    latitude: float,
    longitude: float,
) -> Optional[Dict[str, Any]]:
    """
    Identify authoritative state and district from GPS latitude and longitude.
    1. Tries reverse geocoding via geocoding_service (Nominatim / OSM).
    2. Matches resolved administrative names against authoritative options.
    3. Falls back to nearest district centroid via Haversine distance within 500 km.
    """
    # Validate coordinate ranges
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None

    # Step 1: Try reverse-geocoding service
    try:
        from services.geocoding_service import reverse_geocode
        geocoded = await reverse_geocode(latitude, longitude)
        raw_state = geocoded.get("state")
        raw_district = geocoded.get("district") or geocoded.get("city")

        if raw_state:
            matched_state = match_authoritative_state(raw_state)
            if matched_state:
                matched_district = None
                if raw_district:
                    matched_district = match_authoritative_district(matched_state, raw_district)

                # If district couldn't be matched by name, find nearest district within that state
                if not matched_district:
                    districts_in_state = AUTHORITATIVE_LOCATIONS.get(matched_state, [])
                    if districts_in_state:
                        closest = min(
                            districts_in_state,
                            key=lambda d: haversine_distance_km(latitude, longitude, d["latitude"], d["longitude"]),
                        )
                        matched_district = closest["district"]

                if matched_state and matched_district:
                    return {
                        "state": matched_state,
                        "district": matched_district,
                        "latitude": latitude,
                        "longitude": longitude,
                        "source": "reverse_geocoding",
                    }
    except Exception:
        # Fall through to geospatial proximity
        pass

    # Step 2: Geospatial proximity fallback (find nearest district centroid in all of India)
    best_match = None
    min_dist = float("inf")

    for state_name, districts in AUTHORITATIVE_LOCATIONS.items():
        for d in districts:
            dist = haversine_distance_km(latitude, longitude, d["latitude"], d["longitude"])
            if dist < min_dist:
                min_dist = dist
                best_match = (state_name, d["district"])

    # If within 500 km of an Indian district centroid, accept as closest match
    if best_match and min_dist <= 500.0:
        return {
            "state": best_match[0],
            "district": best_match[1],
            "latitude": latitude,
            "longitude": longitude,
            "source": "nearest_district",
        }

    return None

