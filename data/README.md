# Datos locales (no se versionan)

Coloca aquí o en la raíz del proyecto los Excel de trabajo. Están en `.gitignore`:

- `trabajadores.xlsx`
  - hoja `MASTER_EMPLEADO`
  - hoja `CRONOGRAMA`
  - hoja `RECORD_VACACIONALES`
- `usuarios.xlsx` — correos autorizados, gerencia y rol

Carga a Neon:

```
cd backend
python scripts/generar_sql_neon.py --apply
```

La carpeta `seed/` es opcional (plantillas locales). Los `.xlsx` no se suben a git.
