// API helpers for GAP-1 backend requests.
import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const API = axios.create({
  baseURL: API_BASE_URL,
});

export const runGap1 = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  // Do not set Content-Type manually: the client must send multipart boundary.
  // A bare "multipart/form-data" header breaks parsing and can hang the server.
  const response = await API.post("/run-gap1", formData, {
    timeout: 600_000,
  });
  return response.data;
};

export const getMeetings = async () => {
  const response = await API.get("/meetings");
  return response.data;
};

export const getJobStatus = async (jobId) => {
  const response = await API.get(`/status/${jobId}`);
  return response.data;
};

export const getMeetingResult = async (jobId, options = {}) => {
  const response = await API.get(`/result/${jobId}`, {
    params: options.allowPartial ? { allow_partial: 1 } : undefined,
  });
  return response.data;
};

export const deleteMeeting = async (jobId) => {
  await API.delete(`/meetings/${jobId}`);
};

export const cancelJob = async (jobId) => {
  const response = await API.post(`/jobs/${jobId}/cancel`, null, {
    timeout: 20_000,
  });
  return response.data;
};
