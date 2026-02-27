import axios from "axios";

const API = axios.create({
  baseURL: "http://127.0.0.1:8000",
});

export const runGap1 = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const response = await API.post("/run-gap1", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const getMeetings = async () => {
  const response = await API.get("/meetings");
  return response.data;
};

export const getMeetingResult = async (jobId) => {
  const response = await API.get(`/result/${jobId}`);
  return response.data;
};
