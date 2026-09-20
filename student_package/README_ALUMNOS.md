# Guía para alumnos

Sistema de logística con Cassandra: órdenes, productos y envíos.

## Requisitos previos

- Python 3.8 o superior
- Docker (para Cassandra)
- El ejecutable `validate` en la carpeta `student_package/` (incluido en el paquete de tu SO)

## 1. Configurar el entorno

### Instalar dependencias de Python

```bash
# Crear y activar entorno virtual (recomendado)

# Linux / Mac:
python3 -m venv venv
source venv/bin/activate

# Windows:
python3 -m venv venv
.\venv\Scripts\Activate.ps1

# Instalar dependencias del proyecto
pip install -r requirements.txt
```

### Iniciar Cassandra

Con Docker Compose (recomendado):

```bash
docker compose up -d
# Espera a que el healthcheck pase (puede tardar ~1 min la primera vez)
docker compose ps
```

O con `docker run`:

```bash
docker run --name logistics -p 9042:9042 -d cassandra
# Si ya existe el contenedor:
docker start logistics
```

Espera unos segundos (o hasta ~1 minuto la primera vez) para que Cassandra esté listo.

## 2. Ejecutar la aplicación

```bash
python3 app.py
```

La aplicación muestra un menú interactivo:

- **0**: Poblar datos de ejemplo
- **1**: Órdenes por cliente
- **2**: Productos por orden
- **3–7**: Consultas de envíos
- **8**: Cambiar email
- **9**: Salir

## 3. Validar tu implementación

Usa el paquete correspondiente a tu sistema operativo:

| Sistema | Carpeta / artefacto | Cómo ejecutar |
|---------|---------------------|---------------|
| macOS (Apple Silicon o Intel) | `student_package/` con wrapper | `./student_package/validate` |
| Linux | `student_package/` | `./student_package/validate` |
| Windows | `student_package/` | `.\student_package\validate.exe` |

En **macOS** el paquete incluye `validate` (script), `validate-arm64` y `validate-x86_64`. Ejecuta siempre el wrapper:

```bash
./student_package/validate
```

**Importante**: Ejecuta desde la carpeta raíz del proyecto (donde están `app.py` y `model.py`).

### Guardar el reporte para entrega

```bash
./student_package/validate --output report.txt
```

### Verificar integridad del reporte

```bash
./student_package/validate --verify report.txt
```

## 4. Interpretar el resultado

```
=== Logistics App Report ===
Passed: 10/10

PASS - Option 0 - Populate sample data
PASS - Option 1 - Orders by customer
...
SHA256:abc123...
```

- **Passed: X/10**: Número de opciones correctas.
- **PASS** / **FAIL**: Resultado de cada opción (en FAIL aparece el motivo).
- **SHA256**: Hash para comprobar que el reporte no fue alterado.

## 5. Solución de problemas

| Problema | Posible solución |
|----------|------------------|
| `bad CPU type in executable` | Tienes un binario Mac de otra arquitectura. Usa el **paquete macOS completo** (`validate` + `validate-arm64` + `validate-x86_64`) y ejecuta `./student_package/validate`, no un solo binario suelto. |
| "Could not connect to Cassandra" | Revisa que Docker esté en marcha y el contenedor `logistics` healthy. |
| "No module named 'cassandra'" | Ejecuta `pip install -r requirements.txt` con el venv activo. |
| "Permission denied" | En Linux/Mac: `chmod +x student_package/validate student_package/validate-*`. |
| "No orders found" | Ejecuta primero la opción 0 en la app para poblar datos (el validador también lo intenta solo). |

## Archivos del proyecto

| Archivo | Descripción |
|---------|-------------|
| `app.py` | Aplicación principal (menú). |
| `model.py` | Modelo de datos y consultas a Cassandra. |
| `requirements.txt` | Dependencias de Python. |
| `docker-compose.yml` | Cassandra local. |
| `student_package/validate` | Validador (no modificar). |
