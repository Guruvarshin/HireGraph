import { getApiHeaders, getRecruiterId } from "@/lib/user";


const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";


async function apiFetch(method, endpoint, body = null) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = getApiHeaders();

  const options = {
    method,
    headers,
  };


  if (body && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);


    let responseData;
    try {
      responseData = await response.json();
    } catch (e) {

      responseData = await response.text();
    }


    if (!response.ok) {
      const errorMessage =
        typeof responseData === "object" && responseData.detail
          ? responseData.detail
          : typeof responseData === "string"
            ? responseData
            : `HTTP ${response.status}`;

      throw new Error(errorMessage);
    }

    return responseData;
  } catch (error) {

    throw new Error(`API call failed (${method} ${endpoint}): ${error.message}`);
  }
}


export async function apiGet(endpoint) {
  return apiFetch("GET", endpoint);
}


export async function apiPost(endpoint, body) {
  return apiFetch("POST", endpoint, body);
}


export async function apiPostForm(endpoint, formData) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    "X-Recruiter-ID": getRecruiterId(),

  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: formData,
    });

    let responseData;
    try {
      responseData = await response.json();
    } catch (e) {
      responseData = await response.text();
    }

    if (!response.ok) {
      const errorMessage =
        typeof responseData === "object" && responseData.detail
          ? responseData.detail
          : typeof responseData === "string"
            ? responseData
            : `HTTP ${response.status}`;

      throw new Error(errorMessage);
    }

    return responseData;
  } catch (error) {
    throw new Error(`File upload failed (POST ${endpoint}): ${error.message}`);
  }
}


export async function apiPut(endpoint, body) {
  return apiFetch("PUT", endpoint, body);
}


export async function apiPatch(endpoint, body) {
  return apiFetch("PATCH", endpoint, body);
}


export async function apiDelete(endpoint, body = null) {
  return apiFetch("DELETE", endpoint, body);
}
