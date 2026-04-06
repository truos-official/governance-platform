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

export async function searchCatalog({
  q,
  type,
  sort,
  domain,
  tier,
  jurisdiction,
  measurementMode,
  skip = 0,
  limit = 20,
} = {}) {
  const query = (q ?? "").trim();
  if (!query) return { items: [], total: 0, skip, limit, facets: {} };

  const params = { q: query, skip, limit };
  if (type) params.type = type;
  if (sort) params.sort = sort;
  if (domain) params.domain = domain;
  if (tier) params.tier = tier;
  if (jurisdiction) params.jurisdiction = jurisdiction;
  if (measurementMode) params.measurement_mode = measurementMode;

  const response = await catalogApi.get("/catalog/search", { params });
  return response.data;
}

export async function autocompleteCatalog({
  q,
  type,
  skip = 0,
  limit = 8,
} = {}) {
  const query = (q ?? "").trim();
  if (!query) return { items: [], total: 0, skip, limit };

  const params = { q: query, skip, limit };
  if (type) params.type = type;

  const response = await catalogApi.get("/catalog/autocomplete", { params });
  return response.data;
}

export async function getControlDetail(controlId) {
  const response = await catalogApi.get(`/catalog/controls/${controlId}`);
  return response.data;
}

export async function getRequirementDetail(requirementId) {
  const response = await catalogApi.get(`/catalog/requirements/${requirementId}`);
  return response.data;
}

export async function getCatalogItemDetail(item) {
  const itemType = item?.type;
  const itemId = item?.id;
  if (!itemId || !itemType) {
    throw new Error("Missing item id or type");
  }
  if (itemType === "control") return getControlDetail(itemId);
  if (itemType === "requirement") return getRequirementDetail(itemId);
  throw new Error(`Unsupported item type: ${itemType}`);
}
