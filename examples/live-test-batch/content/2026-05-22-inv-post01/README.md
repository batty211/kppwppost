# รูปสำหรับโพสต์ตัวอย่าง

นำรูปทั้งสามไฟล์มาใส่ในโฟลเดอร์นี้โดยตั้งชื่อดังนี้:

```text
1.jpg  รูป Featured Image
2.jpg  รูปเจ้าหน้าที่ตรวจสอบเอกสาร
3.jpg  รูปแสดงผลการแจ้งที่พักอาศัย
```

`1.jpg` ไม่ต้องอ้างใน Markdown เพราะระบบจะตั้งเป็น Featured Image ให้อัตโนมัติ

`2.jpg` และ `3.jpg` ถูกอ้างในไฟล์
`../2026-05-22-inv-post01.md` และจะถูกอัปโหลดเป็น Gutenberg Image blocks

หลังวางรูปแล้วให้สั่ง:

```bash
kppost generate ./examples/live-test-batch
kppost validate ./examples/live-test-batch
```
