# Roadmap TP4 — Demostración Final (BookUp)

> **Objetivo:** tener BookUp **andando en AWS** el día de la demo, cumpliendo todo lo
> que prometimos en el TP1. La entrega es una **demo en vivo** de la solución
> desplegada, con **evaluación individual** (cada uno defiende la arquitectura y
> responde preguntas). El Terraform **no** se re-evalúa (eso fue la entrega 3), pero
> lo usamos para levantar todo.

**Referencias de las tareas:**
- 📋 **consigna** — lo que nos pide la cátedra (nos evalúan por esto).
- 🙌 **nuestra** — cosas que no nos evalúan, pero las hacemos porque las necesitamos.

---

## Decisiones ya tomadas

- **Elasticidad / desacople:** SNS (notificaciones) **+** autoscaling de ECS. No alcanza con
  el SQS que ya existe (es solo la DLQ del indexador): queremos algo demostrable en vivo.
- **API pública gobernada:** se hace con **Amazon API Gateway** (es lo que propusimos en el
  TP2, y ya sabemos que funciona en el lab porque el `auth-bridge` lo usa).
- **Gaps del TP1:** se implementan **sí o sí** los dos que faltan (API pública y reportes).
- **Seguridad:** no está en la consigna escrita → **confirmar con la cátedra** antes de meterle horas.

---

## ✅ Lo que ya funciona

- Login y registro de usuarios (Cognito)
- Buscador de libros (OpenSearch)
- Disponibilidad cruzada entre todas las sedes
- Panel de bibliotecarios (reservas, retiros, devoluciones)
- Portadas de libros (S3 con versionado)
- La plataforma **ya levanta bien en AWS** con nuestro Terraform

## 📋 Lo que pide la consigna del TP4 (y cómo estamos)

- [x] Autenticación con **Cognito**
- [x] **Terraform** (ya se evaluó en la entrega 3)
- [ ] **Todos los componentes** que prometimos en el TP1 (faltan 2: API pública y reportes)
- [ ] **Elasticidad y desacople** (al menos un SQS o SNS)
- [ ] **Diagrama actualizado** que coincida con lo armado
- [ ] **La solución completa andando** el día de la demo

---

## 🔧 Tareas

Regla de oro: **cada feature se deja andando _en Terraform_ por quien la hace.** No está
terminada hasta que levanta sola con el deploy. Así nadie integra lo de los demás al final.

### 🟡 Lo principal — en paralelo

#### 1. API pública (API Gateway) — 📋 consigna (TP1) — **Valen**
Que otros sistemas/bibliotecas puedan consultar el catálogo, con credenciales + límite de uso.
- **Por dónde empezar:** confirmar en el lab que se puede crear un API Gateway "de verdad"
  (el `auth-bridge` ya usa un HTTP API → ver `terraform/modules/auth/bridge.tf`).
- Nuevo módulo (ej. `terraform/modules/public-api/`) con un API Gateway delante del catálogo,
  exponiendo **solo lectura**: `GET /books`, `/books/search`, `/books/{isbn}`, `/availability`.
- Agregar **API keys + usage plans (throttling)** y métricas por cliente (CloudWatch).

#### 2. Notificaciones (SNS) — 📋 consigna (desacople) — **Mati**
Avisos automáticos, ej: *"tu reserva está lista para retirar"* / *"está por vencer"*.
- **Por dónde empezar:** crear un **SNS topic** en Terraform (ej. `terraform/modules/notifications/`).
- Publicar desde la API en los eventos de reserva (ver `api/app/services/reservation_service.py`).
- Suscripción por email. Permisos vía `LabRole`.
- De paso, **documentar el SQS actual** (es la DLQ del indexador) para el relato de desacople.

#### 3. Autoscaling de ECS — 📋 consigna (elasticidad)
Que la plataforma sume/saque contenedores según la demanda. Hoy corre con 2 tareas fijas.
- **Por dónde empezar:** agregar `aws_appautoscaling_target` + una policy de **target tracking
  por CPU** al servicio ECS (ver `terraform/modules/compute/ecs.tf`, `desired_count` fijo hoy).
- Para la demo: generar carga y mostrar cómo nacen tareas nuevas.

#### 4. Reportes / analítica — 📋 consigna (TP1) — *implementado, falta verificar en el lab*
Un lugar aparte para sacar estadísticas (ej: reservas por sede/mes) sin afectar la app.
- **Por dónde empezar:** lo más barato para el lab es **Athena sobre S3** (evitar Redshift, es caro).
- Exportar datos de DynamoDB a S3 (export o un job chico) y crear una tabla de Athena + **una
  query de ejemplo**. Alternativa: un crawler de Glue.

#### 5. Actualizar el diagrama — 📋 consigna
Que el dibujo coincida con lo armado (ECS, DynamoDB, Cognito **+ las piezas nuevas**).
- **Por dónde empezar:** partir de `docs/arquitectura.drawio.pdf` y sumar API Gateway, SNS y autoscaling.
- ⚠️ Se puede **empezar** en paralelo, pero se **cierra al final**, cuando 1–4 estén definidas.

### 🔴 Para el final (cuando ya está todo junto)

#### 6. Prender todo junto y ensayar la demo — 📋 consigna (demo en vivo)
- Deploy completo (tarda ~20 min) **antes de la clase**, nunca en vivo arrancando de cero.
- Checklist de verificación: `/health`, login, búsqueda, reserva, notificación, API pública, autoscaling.
- **Acordarse de apagar** después (hay un workflow de *destroy*) para cuidar los USD 50 del lab.

#### 7. Reescribir el guión de la demo — 🙌 nuestra
El actual (`TP2/GUION-DEMO.md`) describe la arquitectura vieja (EC2/ASG/RDS). Hay que rehacerlo
para la actual (ECS/DynamoDB/Cognito/SNS/API Gateway/autoscaling).

#### 8. Seguridad — 🙌 nuestra / a confirmar
- **Primero confirmar con la cátedra si es obligatorio** (no está en la consigna escrita).
- Si va: WAF (si el lab lo permite), secrets en SSM/Secrets Manager (hoy en env/tfvars),
  políticas de bucket más finas, y mostrar los security groups encadenados que ya tenemos.

---

## ¿Qué se puede hacer en paralelo?

- **Tareas 1–4: totalmente en paralelo.** Son módulos de Terraform distintos; coordinar solo
  para no editar los mismos archivos, pero cada uno trabaja sobre la base que ya levanta.
- **Tarea 5 (diagrama):** se empieza en paralelo, se cierra al final (depende de 1–4).
- **Tareas 6 y 7:** son al final por naturaleza (necesitan todo junto).
- **Tarea 8:** bloqueada hasta confirmar con la cátedra.

---

*Teoría: cada uno se prepara por su cuenta para la defensa individual.*
