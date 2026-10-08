import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://10.36.224.150:8000';

export const apiClient = axios.create({
  baseURL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default apiClient;
