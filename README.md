# Matt Pocock Codex Skills

이 repo는 [mattpocock/skills](https://github.com/mattpocock/skills)를 Codex 용도로 변환한 결과물입니다.

- 사용한 source commit: [`5d78b`](https://github.com/mattpocock/skills/commit/5d78bd0903420f97c791f834201e550c765699f8)

## Update

원본 repo가 업데이트되면 다음 명령으로 이 Codex용 출력물을 다시 생성합니다.

```bash
# mattpocock의 skills 폴더 안에서 실행
git clone https://github.com/rmekdma/mattpocock.git
./mattpocock/update-from-source.py
cp -r mattpocock ~/.agents/skills

cd mattpocock
git add . && git commit -m "update" && git push origin main
```
