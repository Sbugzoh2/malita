Malita — Home screen hero banner: your photo, used as-is
============================================================

This replaces mobile/assets/hero-student.png with the exact photo you
supplied (person's hands reaching toward floating physics/math
equations) - pixel-identical to what you sent, only re-saved from JPEG
to PNG since the app already references a .png path at that filename.
No cropping, editing, or recoloring.

Used as-is per your explicit confirmation that you own the rights to
this photo.

How to apply
------------
1. Copy this file into your local clone, overwriting the existing one:
     mobile/assets/hero-student.png

2. From your repo root:
     git add mobile/assets/hero-student.png
     git commit -m "Use the provided photo as the Home screen hero banner, as-is"
     git push -u origin claude/math-tutor-app-script-7ac98e

3. Nothing else to run - same filename/path, no code changes needed.

One thing worth knowing: this photo's aspect ratio (642x350, about 1.83:1)
is a bit different from the illustration it replaces (1152x768, 1.5:1).
The Home screen still uses resizeMode="cover" in a fixed 200dp-tall
banner, so it'll still fill the space correctly on every phone width -
just note the crop will land slightly differently (a bit more of the
left/right edges may crop on narrower phones) than the previous image.
If you want that adjusted, let me know and I can help, but I left the
photo itself completely untouched as asked.
