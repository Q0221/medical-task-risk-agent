import { get } from "./http";

/**
 * 档案总览统计
 * @returns {Promise<{ hospital_count, product_count, risk_task_count, high_risk_hospital_count, open_task_count }>}
 */
export function getRecordStats() {
  return get("/records/stats");
}

/**
 * 医院列表
 * @param {{ page?: number, page_size?: number, search?: string, level?: string, region?: string }} params
 * @returns {Promise<{ items: any[], total: number, page: number, page_size: number }>}
 */
export function listHospitals(params = {}) {
  return get("/records/hospitals", params);
}

/**
 * 医院详情（含近期任务、关联产品）
 * @param {number} hospitalId
 * @returns {Promise<any>}
 */
export function getHospitalDetail(hospitalId) {
  return get(`/records/hospitals/${hospitalId}`);
}

/**
 * 医院筛选枚举值
 * @returns {Promise<{ levels: string[], regions: string[] }>}
 */
export function getHospitalOptions() {
  return get("/records/hospitals/options");
}

/**
 * 产品列表
 * @param {{ page?: number, page_size?: number, search?: string, category?: string, business_unit?: string }} params
 * @returns {Promise<{ items: any[], total: number, page: number, page_size: number }>}
 */
export function listProducts(params = {}) {
  return get("/records/products", params);
}

/**
 * 产品详情（含近期任务、关联医院）
 * @param {number} productId
 * @returns {Promise<any>}
 */
export function getProductDetail(productId) {
  return get(`/records/products/${productId}`);
}

/**
 * 产品筛选枚举值
 * @returns {Promise<{ categories: string[], business_units: string[] }>}
 */
export function getProductOptions() {
  return get("/records/products/options");
}
