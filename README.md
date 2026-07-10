# Matt Pocock Codex Skills

이 repo는 [mattpocock/skills](https://github.com/mattpocock/skills)를 Codex 용도로 변환한 결과물입니다.

- 사용한 source commit: [`d5747`](https://github.com/mattpocock/skills/commit/d574778f94cf620fcc8ce741584093bc650a61d3)

## 설치

```bash
install_root="$HOME/.agents/skills/mattpocock"
mkdir -p "$install_root"

rm -rf "$install_root/skills" "$install_root/.codex-plugin"
cp -R skills .codex-plugin "$install_root"/
```

## Update

원본 repo가 업데이트되면 다음 명령으로 이 Codex용 출력물을 다시 생성합니다.

```bash
git clone git@github.com:mattpocock/skills.git
cd skills
git clone git@github.com:rmekdma/mattpocock.git
./mattpocock/update-from-source.py
cd mattpocock
git add . && git commit -m "update" && git push origin main
```
