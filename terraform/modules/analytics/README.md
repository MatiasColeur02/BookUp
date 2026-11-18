# analytics

Reportes y analítica (TP1) sin cargar la app:

```
DynamoDB ──(Lambda exportadora, EventBridge cada hora)──▶ S3 (JSON Lines) ◀── Athena (Glue Catalog)
```

- **Exportador** (`api/app/analytics/exporter.py`): reescribe una foto completa de `reservations`,
  `libraries` y `books` en el bucket privado. Lee por GSI1 (sin `Scan`) y no exporta datos
  personales (solo `user_id`).
- **Glue**: base `<proyecto>_analytics` con una tabla externa por archivo (SerDe JSON).
- **Athena**: workgroup propio con tope de bytes escaneados y 4 queries guardadas
  (reservas por sede y mes, libros más reservados, resultado por sede, demanda por ciudad).

## Demo

```bash
terraform output -raw analytics_export_command | sh    # exporta ya
terraform output -raw analytics_example_query_command | sh
```

O en la consola de Athena: workgroup `<proyecto>-analytics`, pestaña *Saved queries*.
