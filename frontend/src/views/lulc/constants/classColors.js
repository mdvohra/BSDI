/**
 * Matches backend/lulc/app.py CLASS_COLORS + ID2LABEL (land cover class display names).
 */
export const LULC_CLASS_COLORS = {
  'arbor woodland': 'rgb(34, 197, 94)',
  'artificial grassland': 'rgb(163, 230, 53)',
  'dry cropland': 'rgb(251, 146, 60)',
  'garden plot': 'rgb(52, 211, 153)',
  'industrial land': 'rgb(192, 38, 211)',
  'irrigated land': 'rgb(14, 165, 233)',
  lake: 'rgb(59, 130, 246)',
  'natural grassland': 'rgb(132, 204, 22)',
  'paddy field': 'rgb(250, 204, 21)',
  pond: 'rgb(56, 189, 248)',
  river: 'rgb(37, 99, 235)',
  'rural residential': 'rgb(244, 114, 182)',
  'shrub land': 'rgb(101, 163, 13)',
  'traffic land': 'rgb(253, 224, 71)',
  'urban residential': 'rgb(239, 68, 68)',
};

export function lulcColorForClass(name) {
  if (!name) return '#94a3b8';
  const key = String(name).toLowerCase().trim();
  return LULC_CLASS_COLORS[key] || '#94a3b8';
}
