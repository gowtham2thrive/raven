/**
 * Utility functions for currency and numerical formatting.
 */

/**
 * Format an amount in INR Rupees with intelligent unit scaling (Crore, Lakh, K, or INR comma separation).
 *
 * @param {number|null|undefined} amountInRupees
 * @returns {string}
 */
export function formatCurrency(amountInRupees) {
  if (amountInRupees == null || isNaN(amountInRupees)) return '₹0';
  const num = Number(amountInRupees);
  if (num === 0) return '₹0';
  
  if (num >= 10000000) {
    return `₹${(num / 10000000).toFixed(2)}Cr`;
  }
  if (num >= 100000) {
    return `₹${(num / 100000).toFixed(2)}L`;
  }
  if (num >= 10000) {
    return `₹${(num / 1000).toFixed(1)}k`;
  }
  return `₹${num.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

/**
 * Format an amount in Paise (Razorpay native currency unit) to INR Rupees string.
 *
 * @param {number|null|undefined} amountInPaise
 * @returns {string}
 */
export function formatPaise(amountInPaise) {
  return formatCurrency((amountInPaise || 0) / 100);
}
