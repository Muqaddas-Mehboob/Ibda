import { Image } from "expo-image";

const paths = {
  home: '<path d="m3 10 9-7 9 7v10H4V10m5 10v-7h6v7"/>',
  brand: '<path d="m12 3 8 9-8 9-8-9 8-9Z"/><path d="m8 12 4-4 4 4-4 4-4-4Z"/>',
  wand: '<path d="m4 20 12-12 4 4L8 24Z M14 10l4 4M5 3v4M3 5h4m12-4v4m-2-2h4M3 13v4m-2-2h4" transform="translate(1 -2)"/>',
  spark: '<path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z"/>',
  check: '<path d="m7 12 3 3 7-7"/><rect x="3" y="3" width="18" height="18" rx="6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="4"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>',
  chart: '<path d="M4 4v16h16M8 15l4-5 4 2 4-7"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  reach: '<path d="M4 17 10 11l4 3 6-9m-6 0h6v6"/>',
  link: '<path d="m9 15 6-6m-5-3 2-2a5 5 0 0 1 7 7l-2 2M7 11l-2 2a5 5 0 0 0 7 7l2-2"/>',
};

export type StudioIconName = keyof typeof paths;

// SVG artwork is ASCII. Base64 data URIs work with the native image decoder too.
function imageUri(svg: string) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let encoded = "";
  for (let i = 0; i < svg.length; i += 3) {
    const bits = (svg.charCodeAt(i) << 16) | ((svg.charCodeAt(i + 1) || 0) << 8) | (svg.charCodeAt(i + 2) || 0);
    encoded += alphabet[(bits >>> 18) & 63] + alphabet[(bits >>> 12) & 63]
      + (i + 1 < svg.length ? alphabet[(bits >>> 6) & 63] : "=")
      + (i + 2 < svg.length ? alphabet[bits & 63] : "=");
  }
  return `data:image/svg+xml;base64,${encoded}`;
}

export function StudioIcon({ name, color = "#25221F", size = 24 }: {
  name: StudioIconName; color?: string; size?: number;
}) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
  return <Image source={{ uri: imageUri(svg) }} style={{ width: size, height: size }} accessible={false} />;
}
