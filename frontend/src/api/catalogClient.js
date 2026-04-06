import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

const catalogApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

export async function listInterpretations({
  requirementId,
  layer,
  view = "flat",
  skip = 0,
  limit = 50,
} = {}) {
  const params = { view, skip, limit };
  if (requirementId) params.requirement_id = requirementId;
  if (layer) params.layer = layer;

  const response = await catalogApi.get("/catalog/interpretations", { params });
  return response.data;
}

export async function getInterpretationTree({
  requirementId,
  skip = 0,
  limit = 50,
} = {}) {
  return listInterpretations({
    requirementId,
    view: "tree",
    skip,
    limit,
  });
}
