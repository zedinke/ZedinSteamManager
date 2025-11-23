# Automatikus Git Commit és Push

Ez a dokumentum leírja, hogyan működik az automatikus git commit és push mechanizmus.

## Áttekintés

Az automatikus commit és push mechanizmus biztosítja, hogy minden módosítás automatikusan feltöltésre kerüljön a git repository-ba.

## Komponensek

### 1. `scripts/auto_commit.py`

Ez a Python script automatikusan:
- Ellenőrzi a git státuszt
- Hozzáadja az összes módosított fájlt (`git add -A`)
- Létrehoz egy commit-ot automatikus üzenettel
- Pusholja a változtatásokat a remote repository-ba

**Használat:**
```bash
python scripts/auto_commit.py
```

**Egyedi commit üzenettel:**
```bash
python scripts/auto_commit.py "Egyedi commit üzenet"
```

### 2. `.git/hooks/post-commit`

Ez a git hook automatikusan futtatódik minden commit után, és automatikusan pusholja a változtatásokat.

## Automatikus futtatás

### Opció 1: Git Hook (Ajánlott)

A `.git/hooks/post-commit` hook automatikusan futtatódik minden commit után. Ez biztosítja, hogy minden commit automatikusan pusholva legyen.

**Megjegyzés:** A hook csak akkor működik, ha a fájl végrehajtható:
```bash
chmod +x .git/hooks/post-commit
```

### Opció 2: Manuális futtatás

Ha nem szeretnéd, hogy minden commit után automatikusan pusholjon, futtasd manuálisan:

```bash
python scripts/auto_commit.py
```

## Log fájlok

Az automatikus commit és push műveletek logolva vannak a `logs/auto_commit.log` fájlba.

## Biztonsági megjegyzések

⚠️ **FIGYELEM:** Az automatikus push mechanizmus minden commit-ot automatikusan feltölt a remote repository-ba. 

- Győződj meg róla, hogy nem commitolsz érzékeny adatokat (jelszavak, API kulcsok, stb.)
- A `config/app.py` és `.env` fájlok automatikusan kizárva vannak a `.gitignore` által
- Ellenőrizd a módosításokat a commit előtt, ha szükséges

## Kikapcsolás

Ha nem szeretnéd használni az automatikus push mechanizmust:

1. **Git hook kikapcsolása:**
   ```bash
   mv .git/hooks/post-commit .git/hooks/post-commit.disabled
   ```

2. **Vagy töröld a hook fájlt:**
   ```bash
   rm .git/hooks/post-commit
   ```

## Hibaelhárítás

### "Permission denied" hiba

Ha a git hook nem fut, ellenőrizd, hogy végrehajtható-e:
```bash
chmod +x .git/hooks/post-commit
```

### "Nothing to commit" üzenet

Ez normális, ha nincs módosítás a commitoláshoz.

### Push hiba

Ha a push sikertelen:
- Ellenőrizd az internetkapcsolatot
- Ellenőrizd a git hitelesítési beállításokat
- Nézd meg a `logs/auto_commit.log` fájlt a részletekért

