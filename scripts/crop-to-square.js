/**
 * Center-crops an image to a square and saves it as *-square.png
 * Usage: node crop-to-square.js <path-to-image>
 * Example: node scripts/crop-to-square.js "./assets/Home_page_image.png"
 */

import sharp from 'sharp';
import path from 'path';
import fs from 'fs';

const inputPath = process.argv[2];
if (!inputPath || !fs.existsSync(inputPath)) {
  console.error('Usage: node crop-to-square.js <path-to-image>');
  process.exit(1);
}

const dir = path.dirname(inputPath);
const ext = path.extname(inputPath);
const base = path.basename(inputPath, ext);
const outputPath = path.join(dir, `${base}-square.png`);

const meta = await sharp(inputPath).metadata();
const { width: w, height: h } = meta;
const size = Math.min(w, h);
const left = Math.floor((w - size) / 2);
const top = Math.floor((h - size) / 2);

await sharp(inputPath)
  .extract({ left, top, width: size, height: size })
  .toFile(outputPath);

console.log('Saved square image:', outputPath);
