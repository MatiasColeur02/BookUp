# Roadmap: sistema de notificaciones

> **Estado: plan. Nada de esto está implementado.** Cuando una fase se termine, anotarla en la
> sección 11 («Fase N hecha») igual que en `api/ROADMAP.md`, y pasar lo vigente al `README.md`.

Avisarle al lector y a la sede de cada cambio importante de una reserva, con una campana arriba a
la derecha del header que despliega las notificaciones y un número rojo con las que no se leyeron.
**AWS SNS** es el bus por el que viajan los eventos.

**Criterio de todo el documento**: seguir el diseño que ya tiene el repo. Un solo camino de
escritura (el stream de DynamoDB, como el indexador), tabla única, entidades inmutables,
services sin boto3, todo descartable y reconstruible, y nada que tire abajo la API si falla.
Donde había una opción más simple pero que rompía alguna de esas reglas, está anotada como
*alternativa descartada*.

---

## 0. Decisiones tomadas

| Tema | Decisión | Consecuencia |
|---|---|---|
| Plazo de devolución | **Un solo `expires_at`**, como hoy | La devolución vence en la misma fecha que el retiro. «Venció el retiro» y «venció la devolución» son el mismo instante, y los distingue `picked_up` |
| Canales | **Solo campana in-app** | SNS es el bus interno: la Lambda que escribe la bandeja está suscripta directo al topic. Email/SMS quedan enchufables (§12) |
| Mensajería | **Solo SNS, sin SQS** | Un solo topic. Los reintentos son los de la invocación asíncrona de Lambda; lo que falla 3 veces queda en los logs y se descarta (§3.3) |
| Destinatarios de la sede | **Bandeja compartida por sede** | Una bandeja `LIB#<id>`. Si un librarian marca una como leída, queda leída para todos los de esa sede. Los sysadmin no tienen bandeja de sede |
| Tiempo real | **Polling cada 30 s** | `GET /notifications/unread-count` con la pestaña visible; la lista se pide al abrir la campana |
| Eventos | Los 4 pedidos + **retiro confirmado** + **cancelación** | 6 tipos, tabla en §2 |
| Qué baja el número rojo | **Solo clickear cada una** (o «marcar todas como leídas») | Abrir la campana no cambia el contador |
| Vencimiento | **El job solo notifica** | El job programado avisa que venció el plazo pero **no** libera el ejemplar: vencer sigue siendo `POST /reservations/expire` (Mantenimiento) |

Decisiones menores, tomadas acá (revisables):

- **Retención: 90 días** (`NOTIFICATIONS_RETENTION_DAYS`), con TTL de DynamoDB.
- **Frecuencia del job: cada 15 min** (`deadline_scan_minutes` en Terraform). Un aviso de
  vencimiento puede llegar hasta 15 min + 30 s tarde.
- **También se notifica al que hizo la acción.** Si un librarian registra una devolución, la
  bandeja de la sede la recibe igual: es compartida, y para los demás librarians es información
  nueva. Además deja un historial de la sede.
- **El texto se arma en el backend** al escribir la notificación (en castellano, con fechas en
  `America/Argentina/Buenos_Aires`). Así un canal futuro como el email reutiliza el mismo texto.

---

## 1. Diagnóstico: qué hay hoy y qué falta

Lo que el código actual **no** permite detectar, y que el plan tiene que resolver antes de
escribir una sola notificación:

| Problema | Dónde | Por qué importa |
|---|---|---|
| **Nada escribe cuando vence un plazo.** `expires_at` pasa y la base no se entera | `reservation_service.expire_reservations` solo corre a mano (`POST /reservations/expire`); no hay scheduler en `terraform/` | Sin una escritura no hay evento en el stream, y sin evento no hay notificación de «venció el retiro» ni de «venció la devolución» |
| **Vencida = cancelada.** `expire` cierra con `cancelled_at`, igual que `cancel` | `ReservationRepository._close_ops` | No se puede decidir si mandar «se canceló» o «venció el retiro» |
| **Perdido = devuelto/cancelado.** Marcar un ejemplar `lost` cierra su reserva con `returned_at` o `cancelled_at` | `release_lost_copy` | Se mandaría «devolución registrada» por un libro que se perdió |
| **El retiro no tiene fecha.** `mark_picked_up` solo pone `picked_up = true` | `ReservationRepository.mark_picked_up` | La notificación necesita un instante determinista para su id (§5.2) |
| **El seed escribe ~190 reservas.** Con un consumidor del stream, cada una sería una notificación | `seed.py` | Inundaría las bandejas de la demo con historia de hace un año |
| **El stream ya tiene un lector** (el indexador) | `modules/indexer` | DynamoDB Streams admite **dos** lectores simultáneos por shard sin throttling. El notificador es el segundo, y uno futuro tendría que colgarse de SNS (que es justamente para lo que está) |

---

## 2. Eventos y destinatarios

Seis tipos. Cada uno genera **dos** notificaciones: una en la bandeja del lector y una en la de la
sede de la reserva (`reservation.library_id`).

| Tipo | Cuándo | Lector | Sede |
|---|---|---|---|
| `reservation.created` | Se crea la reserva | **Reserva confirmada** — Reservaste «Rayuela» en Biblioteca Sur. Tenés hasta el 20/11 para retirarlo. | **Nueva reserva** — Ana Pérez reservó «Rayuela» (ejemplar #55). Retiro hasta el 20/11. |
| `reservation.picked_up` | El librarian marca el retiro | **Préstamo iniciado** — Retiraste «Rayuela». Devolvelo en Biblioteca Sur antes del 20/11. | **Ejemplar entregado** — Se entregó «Rayuela» (ej. #55) a Ana Pérez. Vence el 20/11. |
| `reservation.cancelled` | Cancelación antes del retiro (lector o sede), o ejemplar perdido con la reserva pendiente | **Reserva cancelada** — Cancelaste tu reserva de «Rayuela». / Biblioteca Sur canceló tu reserva de «Rayuela». / …: el ejemplar ya no está disponible. | **Reserva cancelada** — Ana Pérez canceló la reserva de «Rayuela» (ej. #55). / Se canceló la reserva de… |
| `reservation.pickup_expired` | Pasó `expires_at` sin retiro | **Venció el plazo de retiro** — No retiraste «Rayuela» antes del 20/11. Consultá con Biblioteca Sur si podés extenderlo. | **Retiro vencido** — Ana Pérez no retiró «Rayuela» (ej. #55) antes del 20/11. El ejemplar sigue reservado hasta que extiendas el plazo, la canceles o corra el vencimiento. |
| `reservation.return_overdue` | Pasó `expires_at` con el libro retirado y sin devolver | **Préstamo vencido** — El plazo para devolver «Rayuela» venció el 20/11. Devolvelo en Biblioteca Sur cuanto antes. | **Préstamo en mora** — Ana Pérez no devolvió «Rayuela» (ej. #55); venció el 20/11. |
| `reservation.returned` | El librarian registra la devolución | **Devolución registrada** — Biblioteca Sur registró la devolución de «Rayuela». ¡Gracias! | **Ejemplar devuelto** — Ana Pérez devolvió «Rayuela» (ej. #55): vuelve a estar disponible. |

No notifican: la extensión del plazo, ni marcar `lost` un ejemplar **prestado** (es una acción
interna de la sede; el lector no tiene nada que hacer).

Como hay un solo `expires_at` y el job **no** vence las reservas, una reserva con el retiro vencido
sigue abierta y el ejemplar sigue reservado. Por eso el texto de la sede dice qué puede hacer.

---

## 3. Arquitectura

```
                 API (ECS)          Lambda deadline-scanner  ◄── EventBridge rate(15 min)
                    │                       │
                    │ escribe la reserva    │ escribe la marca «ya avisé que venció»
                    ▼                       ▼
              ┌───────────────────────────────────┐
              │  DynamoDB `bookup` (tabla única)  │
              └───────────────┬───────────────────┘
                              │ stream NEW_AND_OLD_IMAGES
               ┌──────────────┴──────────────┐
               ▼                             ▼
      Lambda indexer (ya existe)    Lambda notifier  (filtro: PK = RES#…)
      → OpenSearch + Redis          detecta la transición (Old vs New image)
                                             │ Publish
                                             ▼
                                  SNS `bookup-reservation-events`
                                     │                 ┊ (futuro: email, Firehose → S3 analítica)
                                     │ suscripción `lambda` (invocación asíncrona)
                                     ▼
                              Lambda inbox-writer
                              arma el texto y escribe las 2 notificaciones
                                     │
                                     ▼
                     DynamoDB: INBOX#USER#<id> / INBOX#LIB#<id>
                                     ▲
                                     │ GET /notifications… (polling 30 s)
                              Frontend: campana 🔔 + número rojo
```

### 3.1 Por qué del stream y no publicando desde el service

*Alternativa descartada*: que `reservation_service.mark_returned` haga `sns.publish` después de
escribir. Es un **dual write**: si la escritura sale y el publish falla (o la tarea muere en el
medio), la devolución existe y la notificación no. Es exactamente lo que el indexador ya evita
(`app/indexer.py`, «Único camino de escritura»). El stream sale atómicamente con la escritura,
y Lambda lo reintenta. También deja a `services` sin saber que SNS existe, igual que no sabe de
OpenSearch.

### 3.2 Para qué está SNS

El notificador podría escribir la bandeja directo. SNS está en el medio para **desacoplar quién
detecta de quién entrega**:

- Un canal nuevo (email, SMS, push, analítica con Firehose → S3 para el ETL de «Próximos pasos»)
  es **una suscripción más**, sin tocar el notificador ni el stream. Esto importa porque el stream
  ya tiene sus dos lectores (§1).
- Los `MessageAttributes` (`event_type`) permiten filter policies por suscripción: el email podría
  suscribirse solo a `return_overdue`.

### 3.3 Por qué SNS directo a la Lambda, sin SQS

La Lambda `inbox-writer` está suscripta al topic con `protocol = "lambda"`. Cómo se comporta:

- **Entrega**: SNS invoca a la Lambda de forma asíncrona. Si Lambda no acepta la invocación
  (throttling del servicio), SNS reintenta con su política para endpoints de AWS, que es muy
  insistente. Cuando Lambda la acepta, para SNS el mensaje ya está entregado.
- **Fallo dentro de la función** (DynamoDB con throttling, un bug): Lambda reintenta **2 veces**
  con backoff (el default de Lambda, sin configurar nada). Si las tres fallan, el evento se descarta y el
  error queda en CloudWatch Logs. No hay destino de fallos: se pierde el aviso, nunca la reserva.
- **Duplicados**: SNS entrega *al menos una vez*, y Lambda puede reintentar un evento que en
  realidad se escribió. La bandeja los descarta igual: el id de cada notificación es
  determinista (§5.2).

*Alternativa descartada*: SNS → SQS → Lambda. Suma tres cosas: el mensaje queda guardado hasta
14 días con redrive nativo desde la DLQ, el procesamiento va en lotes y la concurrencia se puede
acotar. Las tres valen con mucho volumen o cuando perder un mensaje es grave. En BookUp son pocas
reservas por día, y una notificación perdida no rompe nada: la reserva sigue bien en la base y se
ve en «Mis reservas» y en el panel. A cambio, SQS agregaba una cola, una DLQ, la policy de la cola
y un poller más en local. Si el volumen crece, meter SQS entre el topic y la Lambda no toca el
código del handler más allá de cómo desarma el evento.

### 3.4 Por qué el job escribe una marca en vez de notificar

El `deadline-scanner` podría publicar a SNS directamente. En cambio hace un update condicional que
setea `pickup_deadline_notified_at` / `return_deadline_notified_at` en la reserva, y el aviso sale
por el stream como cualquier otro. Tres ventajas:

1. **Un solo camino**: el notificador es el único que publica.
2. **Idempotencia gratis**: la condición `attribute_not_exists(<marca>)` garantiza que dos corridas
   del job (o dos invocaciones concurrentes de EventBridge) avisen una sola vez.
3. **Auditable**: la reserva dice cuándo se avisó.

### 3.5 Las Lambdas nuevas corren fuera de la VPC

Hablan solo con DynamoDB y SNS, que son endpoints públicos de AWS. No tocan Redis ni OpenSearch
(las notificaciones no se cachean, §6.3). Fuera de la VPC no ocupan ENIs ni pasan por el NAT. Si
en el futuro hiciera falta, la VPC ya tiene gateway endpoint de DynamoDB, y SNS necesitaría un
interface endpoint (que cuesta por hora).

---

## 4. Detección de eventos (el notificador)

Una función **pura** `detect(record) -> list[ReservationEvent]` en `app/notifications/events.py`:
recibe un registro del stream y devuelve 0, 1 o 2 eventos. Se testea con registros grabados,
sin AWS. Solo mira ítems `PK = RES#<id>`, `SK = META`; el filtro del event source mapping ya
descarta el resto antes de invocar.

| `eventName` | Condición (Old → New) | Evento | `occurred_at` |
|---|---|---|---|
| `INSERT` | `origin` ≠ `seed` | `created` | `reserved_at` |
| `MODIFY` | `picked_up`: `false → true` | `picked_up` | `picked_up_at` (nuevo, §5.1) |
| `MODIFY` | `cancelled_at` aparece y `close_reason ∈ {cancelled, lost}` | `cancelled` | `cancelled_at` |
| `MODIFY` | `cancelled_at` aparece, `close_reason = expired`, y Old **no** tenía `pickup_deadline_notified_at` | `pickup_expired` | `expires_at` |
| `MODIFY` | aparece `pickup_deadline_notified_at` | `pickup_expired` | `expires_at` |
| `MODIFY` | aparece `return_deadline_notified_at` | `return_overdue` | `expires_at` |
| `MODIFY` | `returned_at` aparece y `close_reason = returned` | `returned` | `returned_at` |
| `MODIFY` | `returned_at` aparece y `close_reason = lost` | — (interno de la sede) | |
| `REMOVE` | — (las reservas no se borran nunca) | — | |

La fila de `expired` sin marca cubre el caso en que un sysadmin corre «vencer reservas» antes de
que el job pase: la reserva sale de GSI4, el job ya no la ve, y el aviso tiene que salir igual.
Si ya había marca, no se repite.

El mensaje que se publica (también es el contrato con cualquier suscriptor futuro):

```json
{
  "event_id": "r123.pickup_expired.20261120T235959Z",
  "type": "reservation.pickup_expired",
  "occurred_at": "2026-11-20T23:59:59Z",
  "actor": "system",
  "reservation": {
    "id": 123, "user_id": 7, "library_id": 3, "physical_book_id": 55,
    "isbn": "9788437604572", "expires_at": "2026-11-20T23:59:59Z"
  }
}
```

`actor` ∈ `user | library | system`, y sale de `cancelled_by` (§5.1). `MessageAttributes`:
`event_type` (String). El `event_id` es **determinista**: si el stream reentrega el registro, el
evento es el mismo y la bandeja lo descarta (§5.2). Para `pickup_expired` y `return_overdue` lleva
el `expires_at`, así una extensión seguida de un nuevo vencimiento genera un evento distinto.

El notificador también procesa un segundo tipo de registro: el `REMOVE` por TTL de una
notificación **no leída** (`userIdentity.principalId = dynamodb.amazonaws.com`). Ahí no publica
nada: descuenta 1 del contador de esa bandeja (§5.3).

---

## 5. Modelo de datos

### 5.1 Cambios en `Reservation`

Atributos nuevos, todos opcionales (los ítems existentes siguen siendo válidos):

| Atributo | Lo escribe | Para qué |
|---|---|---|
| `close_reason`: `cancelled \| expired \| returned \| lost` | `_close_ops` (cada llamador pasa el suyo) | Distinguir vencida de cancelada, y perdida de devuelta |
| `cancelled_by`: `user \| library` | `cancel_reservation` (según el `viewer` sea el dueño o staff) | «Cancelaste» vs. «La sede canceló» |
| `picked_up_at` | `mark_picked_up` | `occurred_at` determinista. De paso, el panel puede mostrar cuándo se retiró |
| `pickup_deadline_notified_at` | `deadline-scanner` | Marca idempotente (§3.4) |
| `return_deadline_notified_at` | `deadline-scanner` | Idem |
| `origin`: `seed` | `seed.py` | El notificador ignora los `INSERT` sembrados (§9.3) |

`update_expiry` además hace `REMOVE pickup_deadline_notified_at`: si la sede extiende un retiro
que ya había vencido, el próximo vencimiento tiene que volver a avisar.

Métodos nuevos del repository:

- `list_past_due(now)`: el mismo Query sobre GSI4 que `list_expired`, **sin** el filtro de
  `picked_up` (devuelve pendientes y prestadas vencidas). GSI4 proyecta `ALL`, así que no hace
  falta un `BatchGet`.
- `mark_deadline_notified(reservation_id, kind, seen_expires_at, at)`: update condicionado a
  `open AND picked_up = :expected AND expires_at = :seen AND attribute_not_exists(<marca>)`. La
  condición sobre `expires_at` evita avisar un vencimiento que una extensión acaba de correr.

`close_reason` también puede viajar en el esquema `Reservation` de la API, y entonces
`ReservationStatusBadge` puede mostrar «Vencida» en vez de «Cancelada». Es opcional y no lo
necesita la campana.

### 5.2 La bandeja

Una partición por bandeja, en la misma tabla (`keys.py` es el único lugar que conoce el formato):

| PK | SK | Atributos |
|---|---|---|
| `INBOX#USER#<user_id>` | `NOTIF#<occurred_at ISO>#<event_id>` | `type`, `title`, `body`, `reservation_id`, `library_id`, `isbn`, `created_at` (= `occurred_at`), `read_at?`, `read_by?`, `ttl_epoch` |
| `INBOX#LIB#<library_id>` | `NOTIF#<occurred_at ISO>#<event_id>` | idem |
| `INBOX#USER#<id>` / `INBOX#LIB#<id>` | `UNREAD` | `unread` (número) |

- **Orden**: el SK empieza por la fecha, así que `Query(ScanIndexForward=False, Limit=20)` trae las
  más nuevas. Paginación con `LastEvaluatedKey` (cursor opaco en base64url).
- **Id público** = el SK en base64url. El cliente no lo interpreta: marcar como leída es un
  `UpdateItem` directo, sin buscar.
- **Idempotencia**: el `Put` va con `attribute_not_exists(PK)`. Como el SK sale del evento
  (`occurred_at` + `event_id`, los dos deterministas), un evento repetido choca contra la condición
  y se descarta.
- **Sin GSI nuevos.** Los ítems no llevan `GSI*`, así que no entran en ningún índice. Agregar un GSI
  obligaría a recrear la tabla (`table.py` no repara índices).
- **Snapshot**: el título del libro, el nombre de la sede y el del lector se copian al escribir. Si
  después se renombra el libro, la notificación vieja conserva el nombre de entonces. Es un
  mensaje histórico, no una vista.
- **`read_by`** (user id) en la bandeja de la sede, para que el panel pueda mostrar «leída por…».

### 5.3 El contador de no leídas

El polling pregunta cada 30 s cuántas hay sin leer. Contarlas sería un Query con filtro sobre toda
la bandeja (hasta 90 días): con polling, eso no escala. Se mantiene un contador:

| Operación | Transacción |
|---|---|
| Entregar un evento | `Put` notif lector (condicional) + `ADD unread 1` lector + `Put` notif sede (condicional) + `ADD unread 1` sede. **Una sola transacción de 4 ítems**: o llegan las dos o ninguna |
| Marcar una como leída | `Update` notif `SET read_at, read_by` con `attribute_not_exists(read_at)` + `ADD unread -1` |
| Marcar todas | Query de las no leídas (filtro `attribute_not_exists(read_at)`), en lotes de hasta 99 notifs + 1 `ADD unread -k` por transacción |
| TTL borra una no leída | El notificador ve el `REMOVE` y hace `ADD unread -1` (§4) |

Defensas contra la deriva: la API devuelve `max(unread, 0)`, y «marcar todas» deja el contador
en 0 si al terminar no quedan no leídas.

Si la entrega falla porque el usuario fue borrado entre medio, se escribe solo la notificación
de la sede.

### 5.4 TTL

`ttl_epoch` = `occurred_at` + 90 días, en epoch (segundos). El nombre no es `ttl` porque `TTL` es
palabra reservada en las expresiones de DynamoDB. Solo lo llevan los ítems `NOTIF#`: reservas,
libros y usuarios no se tocan. Se activa en `table.py` (`update_time_to_live`, idempotente) y en
`modules/database` (bloque `ttl`). DynamoDB borra con hasta ~48 h de atraso, así que el listado
filtra `ttl_epoch > now`. DynamoDB Local acepta la configuración pero no conviene contar con que
borre: en local no importa.

---

## 6. API

### 6.1 Endpoints

| Método | Ruta | Descripción | Acceso |
|---|---|---|---|
| GET | `/notifications?scope=me\|library&limit=20&cursor=` | Página de la bandeja, de la más nueva a la más vieja | autenticado; `library` solo librarian con sede |
| GET | `/notifications/unread-count` | `{ "me": 3, "library": 5 }` (`library: null` si no tiene bandeja de sede) | autenticado |
| PATCH | `/notifications/{scope}/{id}/read` | Marcar una como leída (idempotente: si ya estaba leída, 200 igual) | idem |
| POST | `/notifications/{scope}/read-all` | Marcar todas como leídas. Devuelve `{ "marked": n }` | idem |

Esquema `Notification`:

```json
{
  "id": "Tk9USUYjMjAyNi0xMS0yMF...",
  "type": "reservation.return_overdue",
  "title": "Préstamo en mora",
  "body": "Ana Pérez no devolvió «Rayuela» (ej. #55); venció el 20/11.",
  "reservation_id": 123,
  "library_id": 3,
  "created_at": "2026-11-20T23:59:59Z",
  "read_at": null,
  "read_by": null
}
```

`limit` ≤ 50 (422 si no). Un `cursor` inválido da 422, no 500.

### 6.2 Autorización

- `scope=me` → la bandeja `INBOX#USER#<viewer.id>`. Todos los roles tienen una: un librarian o un
  sysadmin también puede reservar.
- `scope=library` → `INBOX#LIB#<viewer.library_id>`, solo si `viewer.role is librarian` y tiene
  `library_id`. Si no, `ForbiddenError` (403). La sede sale **del usuario, no del request**: no
  hay parámetro `library_id` que alguien pueda cambiar para leer la bandeja de otra sede.
- Si a un librarian lo mueven de sede, desde su request siguiente ve la bandeja de la nueva (el
  `User` se recarga en cada request).

Es una regla de rol más la sede del propio usuario, sin cargar ningún recurso: va en
`notification_service` (que recibe el `viewer`), como `_assert_can_manage`.

### 6.3 Sin cache

Igual que `/reservations` y `/auth/me`, la respuesta depende del usuario del token: una entrada
compartida filtraría datos. Además el `unread-count` son dos `GetItem`, más baratos que ir a
Redis y volver. Tampoco aplica rate limiting: el polling es tráfico autenticado y acotado.

### 6.4 Archivos

- `controllers/notification_controller.py`, esquemas en `schemas.py` y registro en `main.py`.
- `services/notification_service.py`: `list_inbox`, `unread_counts`, `mark_read`, `mark_all_read`
  (lado API) y `deliver(event)` (lado inbox-writer), más `scan_deadlines(now)` (lado job).
- `persistence/repositories/notification_repository.py`.
- `openapi.yml`: los 4 endpoints y el esquema.

---

## 7. Frontend

### 7.1 Dónde va la campana

Con sesión abierta, `SessionMenu` hoy devuelve `null`: el lugar arriba a la derecha está libre.
Pero el header tiene dos layouts (`index.css`, `.app-header` y `.app-header-top`):

- **< 900 px** (columna): `.app-header-top` = marca | sesión, y la navegación abajo. La campana va
  a la derecha de esa fila. Funciona sin tocar nada.
- **≥ 900 px** (una fila): `.app-header-top` es `flex: 0 0 auto`, así que la sesión queda **pegada a
  la marca**, a la izquierda de la navegación. Ahí la campana no quedaría a la derecha.

Solución: `.app-header` pasa a ser un **grid con áreas**, y la marca, la navegación y un nuevo
`.header-actions` (campana + `SessionMenu`) son hijos directos (`.app-header-top` desaparece o pasa
a `display: contents`):

```css
.app-header { display: grid; grid-template-areas: "brand actions" "nav nav"; }
@media (min-width: 900px) {
  .app-header { grid-template-areas: "brand nav actions"; grid-template-columns: auto 1fr auto; }
}
```

Sin sesión, `.header-actions` muestra «Ingresar / Crear cuenta» como hoy, y la campana no se
renderiza.

### 7.2 Componentes

| Archivo | Qué hace |
|---|---|
| `components/icons.tsx` | `BellIcon`, con el mismo `base` (24×24, trazo 2, `currentColor`) que los demás |
| `context/NotificationsContext.tsx` | El polling y los contadores. Expone `counts`, `total`, `refresh()`, `refreshSoon()`. Va dentro de `SessionProvider` en `main.tsx` |
| `components/NotificationBell.tsx` | El botón con el número rojo; abre y cierra el panel |
| `components/NotificationPanel.tsx` | El desplegable: encabezado, pestañas, lista, «Ver más», estados vacío, de carga y de error |
| `components/NotificationItem.tsx` | Una notificación: ícono por tipo, título, cuerpo, hace cuánto, resaltado si no está leída |
| `lib/notifications.ts` | Tipo → ícono/tono, destino al clickear, `formatBadge(n)` |
| `api.ts`, `types.ts` | `listNotifications`, `getUnreadCount`, `markNotificationRead`, `markAllNotificationsRead` y sus tipos |
| `index.css` | Bloque «Notificaciones» con `.bell`, `.bell-badge`, `.notif-panel`, `.notif-item` |

### 7.3 El número rojo

- Total = `me + (library ?? 0)`. Con 0 no se muestra; con más de 9, «9+».
- Círculo `var(--danger)` con texto `#fff`, `min-width: 18px`, `border-radius: var(--radius-full)`,
  arriba a la derecha del ícono, con un borde de 2 px del color del fondo del header para
  «recortarlo» sobre la campana. Los tokens ya resuelven el modo oscuro.
- Cuando sube, una animación corta de escala (`--dur-base`, `--ease-out`), anulada con
  `prefers-reduced-motion`.
- Accesible: `aria-label="Notificaciones, 3 sin leer"` en el botón (el número visual es
  `aria-hidden`), `aria-expanded`, `aria-haspopup="dialog"`.

### 7.4 El desplegable

```
┌──────────────────────────────────────────┐
│ Notificaciones     Marcar todas como leídas│
│ [ Mías · 2 ] [ Sede · 5 ]                │  ← pestañas solo si hay bandeja de sede
├──────────────────────────────────────────┤
│ ● ⚠ Préstamo en mora           hace 5 min │  ← no leída: fondo --accent-soft + punto
│     Ana Pérez no devolvió «Rayuela»…      │
│   ✓ Ejemplar devuelto          hace 2 h   │  ← leída: fondo normal
│     Juan Gómez devolvió «Ficciones»…      │
│                 Ver más                   │
└──────────────────────────────────────────┘
```

- Pestañas con la clase `.segmented` que ya usa la navegación. Un librarian ve «Mías» y «Sede»
  (abre en «Sede», que es su trabajo); el resto ve solo su lista, sin pestañas.
- Tono por tipo: `created` → `--accent`, `picked_up` y `returned` → `--success`, `cancelled` →
  `--neutral`, `pickup_expired` → `--warning`, `return_overdue` → `--danger`.
- Hora relativa con `Intl.RelativeTimeFormat("es")`, y la fecha completa en el `title`.
- **Click en una notificación** → `PATCH …/read` (optimista: baja el contador al instante y lo
  revierte con un toast de error si falla) y navega: `scope=me` → `/mis-reservas?reserva=<id>`,
  `scope=library` → `/panel?reserva=<id>`. `MyReservationsView` y `LibrarianPanel` leen ese
  parámetro: hacen scroll a la fila, la resaltan y, en el panel, abren `ReservationManageModal`.
  Abrir el panel **no** marca nada (decisión §0).
- «Marcar todas como leídas» actúa sobre la pestaña visible. En la sede pide confirmación con
  `ConfirmContext`, porque las marca para todos los librarians.
- Carga con `Skeleton`, error con `ErrorBanner` y «Reintentar», y un estado vacío («No tenés
  notificaciones»).
- Se cierra con Escape (devuelve el foco a la campana), con click afuera y al navegar.
  `role="dialog"` con `aria-label`.
- Desktop: popover de 380 px anclado a la campana, `--shadow-lg`, `--radius-lg`, alto máximo 70vh
  con scroll interno, `z-index` por encima de `--z-header`. ≤ 700 px: hoja de ancho completo
  debajo del header.

### 7.5 El polling

- Cada **30 s** solo con `document.visibilityState === "visible"`. Al volver a la pestaña o al
  `focus`, pide en el momento. Sin sesión no corre.
- Si falla, *backoff* (30 → 60 → 120 s, tope 5 min) y la campana conserva el último número. Un
  401 ya lo maneja el interceptor de `api.ts`.
- La lista se pide al abrir el panel y se refresca si el contador cambia mientras está abierto.
- **`refreshSoon()`**: después de una acción propia (reservar, cancelar, retirar, devolver) pide el
  contador a los ~3 s. La cadena stream → notifier → SNS → inbox-writer tarda unos segundos, y
  sin esto el usuario esperaría hasta 30 s para ver la notificación de lo que acaba de hacer.

---

## 8. Infraestructura en AWS

### 8.1 Módulo `terraform/modules/notifications`

| Recurso | Configuración |
|---|---|
| `aws_sns_topic` `${prefix}-reservation-events` | Estándar (no FIFO: el orden no importa y la idempotencia está en la bandeja). `kms_master_key_id = "alias/aws/sns"` |
| `aws_sns_topic_subscription` | `protocol = "lambda"`, `endpoint` = el ARN de `inbox-writer` |
| `aws_lambda_permission` (SNS) | `principal = "sns.amazonaws.com"`, `source_arn` = el topic. Sin esto, SNS no puede invocar la Lambda y la suscripción falla en silencio |
| `aws_lambda_function` × 3 (`for_each`) | `notifier`, `inbox-writer`, `deadline-scanner`. Mismo zip que el indexador (`module.api_package`), `python3.12`, rol `LabRole`, **sin** `vpc_config` (§3.5) |
| `aws_lambda_event_source_mapping` stream → `notifier` | `starting_position = "LATEST"`, `bisect_batch_on_function_error` y reintentos 5: un registro que falla siempre se aísla y se saltea en vez de congelar el shard. `filter_criteria`: `{"dynamodb":{"Keys":{"PK":{"S":[{"prefix":"RES#"}]}}}}` y otro patrón para los `REMOVE` de `INBOX#` por TTL. Sin filtro, la Lambda se invocaría por cada escritura de la tabla |
| `aws_cloudwatch_event_rule` + `target` + `aws_lambda_permission` | `schedule_expression = "rate(${var.deadline_scan_minutes} minutes)"` → `deadline-scanner` |
| `aws_cloudwatch_log_group` × 3 (`for_each`) | Con `log_retention_days`, como el resto |

Fuera del módulo:

- `modules/database/dynamodb.tf`: `ttl { attribute_name = "ttl_epoch", enabled = true }`.
- `organization/main.tf`: `module "notifications"`, que recibe `table_name`, `table_stream_arn`, el
  zip y `lab.arn`. Variables nuevas: `deadline_scan_minutes` (default 15) y
  `notifications_retention_days` (default 90).
- El indexador puede sumar su propio `filter_criteria` (`BOOK#` y `COPY#`). Es opcional, pero ahora
  la tabla también escribe ítems `INBOX#` que el indexador recibe y descarta.

Entorno de las tres Lambdas: `DYNAMO_TABLE`, `NOTIFICATIONS_TOPIC_ARN`,
`NOTIFICATIONS_RETENTION_DAYS`, `NOTIFICATIONS_TIMEZONE`. La API no necesita ninguna variable
nueva: solo lee la bandeja.

Para la tercera entrega, el módulo suma un módulo propio más, `for_each` sobre las Lambdas y los
log groups, y funciones (`jsonencode` en el filtro, `merge`
en el entorno, `format`).

### 8.2 AWS Academy (Learner Lab)

Según lo que ya se probó (ver la memoria del proyecto), el lab niega OpenSearch gestionado, Cloud
Map y parte de S3, y no deja crear roles IAM. Lo que este plan usa:

| Servicio | Estado | Cómo comprobarlo antes de la fase 7 |
|---|---|---|
| Lambda + ESM de stream | Ya funciona (indexador) | — |
| `lambda:AddPermission` (SNS y EventBridge invocando Lambdas) | Ya funciona (API Gateway del puente) | — |
| SNS (topic, subscription, publish) | **A verificar** | `aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::<acct>:role/voclabs --action-names sns:CreateTopic sns:Subscribe sns:Publish sns:SetTopicAttributes` |
| `sns:Publish` desde `LabRole` | **A verificar** | Lo necesita el notificador para publicar los eventos. Mismo comando con `--policy-source-arn` del `LabRole` |
| EventBridge (rule + target) | **A verificar** | Idem con `events:PutRule events:PutTargets` |

Ninguna pieza necesita un rol propio: SNS invoca la Lambda con un permiso basado en recursos
(`aws_lambda_permission`), igual que EventBridge. Por eso se usa una **rule** de EventBridge y no
**EventBridge Scheduler**, que sí necesita un rol que asuma él.

Si SNS estuviera bloqueado, el plan B es que el notificador invoque al `inbox-writer` de forma
asíncrona (`lambda:InvokeFunction` con `InvocationType=Event`): mismos reintentos y mismo handler,
sin el fan-out. Hay que decidirlo en la fase 7, no antes.

### 8.3 Costo

Despreciable a esta escala: SNS tiene 1 M de publicaciones gratis por mes y no cobra la entrega a
Lambda; la rule programada no cobra; con polling cada 30 s, 100 usuarios conectados son ~6.000 `GetItem` por hora (On-Demand:
centavos por mes); las tres Lambdas entran en la capa gratuita.

---

## 9. Desarrollo local

### 9.1 El bus

Una abstracción mínima en `app/notifications/bus.py`, elegida con `NOTIFICATIONS_BUS`:

| Valor | Publica en | Se usa en |
|---|---|---|
| `sns` | El topic de `NOTIFICATIONS_TOPIC_ARN` | AWS |
| `inline` | Arma el mismo mensaje y llama a `inbox_writer.handler` en el mismo proceso | compose y `pytest` |
| vacío | Nada: las notificaciones quedan apagadas | Como Redis/S3 sin configurar: la API anda igual |

`inline` no se saltea el formato: serializa el mensaje y lo envuelve en un evento con la forma
del que SNS le pasa a Lambda (`Records[].Sns.Message`), así que en local corre el mismo
`inbox_writer.handler` que en AWS. Lo único que no se ejercita en local es el `Publish` real.

*Alternativa descartada*: LocalStack como stand-in de SNS, como MinIO lo es de S3. Sin SQS no hay
cola que leer: LocalStack tendría que empujar cada mensaje a un endpoint HTTP del contenedor (una
suscripción `http` y un servidor más), y la imagen puede pedir token de cuenta según la versión.
Para cubrir solo el `Publish`, no vale la pena.

### 9.2 Compose

Un solo servicio nuevo, con el mismo patrón que el `indexer`:

| Servicio | Para qué |
|---|---|
| `notifier` | `python -m app.notifications.local`, con `NOTIFICATIONS_BUS=inline`. En dos hilos: (1) lee el stream de DynamoDB Local (reutiliza el poller de `indexer.run`) y llama a `notifier.handler`, que a través del bus inline termina en `inbox_writer.handler`; (2) corre `deadline_scanner.handler` cada 60 s |

### 9.3 Seed

- Las reservas sembradas llevan `origin = "seed"` y el notificador ignora esos `INSERT`. Sin esto,
  sembrar en AWS (que pasa con el notificador ya desplegado) generaría ~380 notificaciones de
  historia. Hay que confirmar que el seed escriba las reservas **ya en su estado final** (solo
  `INSERT`s); la función `add` de `seed.py` arma las entidades completas, así que debería.
- Los `MODIFY` sobre reservas sembradas **sí** notifican. Al primer paso del job, las reservas
  sembradas en mora y con el retiro vencido generan sus avisos, y `sur@` y `ana@` ven la campana
  con contenido en la demo sin escribir notificaciones a mano.
- Además, el seed escribe un puñado de notificaciones leídas para `ana@` y para la Biblioteca Sur
  (deterministas, como todo el seed), para que se vea la diferencia leída/no leída.

---

## 10. Estructura de archivos

```
api/app/
  notifications/                  # entradas de Lambda y runner local (como indexer.py)
    __init__.py
    events.py                     # detect(record) → eventos. Puro, sin I/O
    bus.py                        # sns | inline
    notifier.py                   # handler del stream → bus
    inbox_writer.py               # handler de SNS (Records[].Sns.Message) → notification_service.deliver
    deadline_scanner.py           # handler de EventBridge → notification_service.scan_deadlines
    messages.py                   # textos en castellano (tabla de §2) y formato de fechas
    local.py                      # los dos loops para compose
  services/notification_service.py
  persistence/repositories/notification_repository.py
  persistence/keys.py             # + inbox_pk, notif_sk, UNREAD
  persistence/table.py            # + TTL
  controllers/notification_controller.py
api/tests/
  test_notification_events.py     # detect() con registros grabados
  test_notification_inbox.py      # deliver, idempotencia, contador
  test_notification_api.py        # endpoints y autorización
  test_deadline_scanner.py
frontend/src/
  context/NotificationsContext.tsx
  components/NotificationBell.tsx
  components/NotificationPanel.tsx
  components/NotificationItem.tsx
  lib/notifications.ts
terraform/modules/notifications/
  topics.tf  lambdas.tf  schedule.tf  variables.tf  outputs.tf  README.md
```

`tzdata` se suma a `requirements.txt`: `zoneinfo` necesita la base de zonas y no conviene depender
de que el runtime de Lambda la traiga.

---

## 11. Fases de ejecución

Cada fase deja el sistema andando, y las fases 1–4 no necesitan AWS.

### Fase 1 — La reserva cuenta lo que pasó
- `close_reason`, `cancelled_by`, `picked_up_at` y `origin` en `Reservation` y en los repositories
  (`_close_ops`, `cancel`, `mark_returned`, `release_lost_copy`, `expire`, `mark_picked_up`).
- `list_past_due`, `mark_deadline_notified` y el `REMOVE` de la marca en `update_expiry`.
- `seed.py` marca `origin = "seed"`.
- **Hecho cuando**: la suite actual sigue verde y hay tests nuevos de cada `close_reason`, de la
  marca condicional (incluida la carrera con una extensión) y de que extender borra la marca.

> **Fase 1 hecha.** Desvíos y detalles respecto del plan: los valores son enums en
> `entities.py` (`CloseReason`, `CancelledBy`, y `DeadlineKind` con `pickup` / `return_`, porque
> `return` es palabra reservada de Python), y `origin` es un `str` con la constante `SEED_ORIGIN`.
> `mark_picked_up` y `cancel` aceptan `at` / `by` opcionales; `cancelled_by` es `user` cuando
> cancela el dueño **aunque sea staff de la sede**. `create` descarta toda la historia que
> mande el llamador (como ya hacía con `picked_up`). El seed además escribe `close_reason`,
> `cancelled_by` y `picked_up_at` (= `reserved_at` + 1 día, sin pasar por el RNG para no cambiar
> el dataset), así las reservas sembradas se ven igual que las de la API. `close_reason` todavía
> no viaja en `ReservationOut`.

### Fase 2 — Detección
- `notifications/events.py` con la tabla de §4.
- **Hecho cuando**: un test por fila de la tabla, con registros del stream grabados de DynamoDB
  Local (no armados a mano: el formato `{"S": …}` engaña), más el `INSERT` sembrado ignorado y el
  `expired` con y sin marca previa.

> **Fase 2 hecha.** `detect` devuelve `ReservationEvent` (dataclass inmutable) con
> `EventType` y `Actor` como enums; `event_id` y `to_message()` (el contrato de §4) ya están, así
> la fase 5 solo serializa. Detalles respecto del plan: `actor` de `created` es `user`, de
> `picked_up`/`returned` es `library`, y de `cancelled` sale de `cancelled_by` (sin él, o por
> `lost`, `library`). Una reserva cerrada **sin** `close_reason` (escrita por código previo a la
> fase 1) se toma como cancelada o devuelta según la columna, y un retiro sin `picked_up_at` usa
> el `ApproximateCreationDateTime` del registro (fijo ante reentregas). `keys.is_reservation_pk`
> es nuevo. Los tests (`tests/test_notification_events.py`) no usan registros grabados en un
> archivo sino **capturados en vivo**: escriben por los repositories sobre una tabla propia y le
> pasan a `detect` lo que devuelve el stream de DynamoDB Local; incluye que un seed completo
> (193 `INSERT`s) no produce ningún evento. El `REMOVE` por TTL de las notificaciones no leídas
> (§4, último párrafo) queda para la fase 3, cuando existan los ítems `INBOX#`.

### Fase 3 — Bandeja
- Claves, `NotificationRepository` (entrega en transacción, listado paginado, leer una, leer todas,
  descontar), `messages.py`, `notification_service.deliver`, TTL en `table.py`.
- **Hecho cuando**: entregar el mismo evento dos veces deja una notificación por bandeja y el
  contador en 1; marcar una como leída dos veces descuenta una sola vez; «leer todas» deja 0; un
  usuario borrado no rompe la entrega a la sede.

> **Fase 3 hecha.** Detalles respecto del plan: la entidad es `Notification` (con `InboxKind`
> `user`/`library`) y lleva `delete_after`, que el repository escribe como `ttl_epoch`. La
> entrega lleva un `ConditionCheck` sobre el `User` en la misma transacción: si el lector se
> borró entre la lectura y la escritura, `deliver` reintenta solo con la sede. «Leer todas»
> pone el contador en 0 condicionado al valor leído, para no pisar una entrega concurrente. El
> id y el cursor opacos se rearman con la PK de la bandeja *del que pregunta* (uno ajeno no lee
> nada), y uno mal formado es `InvalidReferenceError` (persistencia → 422 en la fase 4).
> **Cambio al contrato de §4**: el bloque `reservation` del mensaje suma `close_reason`; sin él
> no se distingue «el ejemplar se perdió» de «la sede canceló», ni un vencimiento ya cerrado de
> uno avisado con la reserva abierta (el texto de la sede cambia: no dice «sigue reservado» si
> ya no lo está). `ReservationEvent.from_message` es el inverso de `to_message` y valida el
> `event_id`. El `REMOVE` por TTL de una no leída se reconoce con
> `events.expired_unread_inbox(record)` (pendiente de la fase 2) y se descuenta con
> `NotificationRepository.decrement_unread`; conectarlos es de la fase 5. `tzdata` en
> `requirements.txt` (hay que rebuildear la imagen).

### Fase 4 — API
- Los 4 endpoints, esquemas, `openapi.yml`.
- **Hecho cuando**: hay tests de que un customer no puede leer `scope=library` (403), un librarian
  ve solo la de su sede y un sysadmin no tiene bandeja de sede; de cursor inválido (422) y
  `limit` > 50 (422).

> **Fase 4 hecha.** `GET /notifications` devuelve `{ "items": [...], "next_cursor": … }`
> (`NotificationPage`). La autorización vive en `notification_service._inbox` con el enum
> `Scope` (`me`/`library`); un librarian **sin** sede tampoco tiene bandeja de sede (403, y
> `library: null` en el contador). `InvalidReferenceError` → 422 en `main.py`. Un id de otra
> bandeja da 404 al marcarlo (no 403: no se revela que exista). `cursor` e id tienen techo de
> 512 caracteres. Tests en `tests/test_notification_api.py`, incluido que un librarian movido de
> sede ve la bandeja nueva desde el request siguiente.

### Fase 5 — Pipeline local
- `bus.py`, los tres handlers, `local.py`; servicio `notifier` en `docker-compose.yml`;
  `.env.example`.
- **Hecho cuando**: con `docker compose up`, reservar desde la API hace aparecer las dos
  notificaciones en ~2 s, y una reserva con `expires_at` en el pasado genera el aviso al minuto.
  `inbox_writer.handler` tiene tests con un evento SNS real grabado (el formato
  `Records[].Sns.Message` es lo que el bus inline imita, y conviene que no diverja).

> **Fase 5 hecha.** Handlers de Lambda: `app.notifications.notifier.handler` (stream),
> `app.notifications.inbox_writer.handler` (SNS) y `app.notifications.deadline_scanner.handler`
> (EventBridge); cada uno tiene un `process(db, …)` que es lo que testean los tests y lo que usa
> el runner local. `scan_deadlines` vive en `notification_service` y saltea las reservas que ya
> tienen la marca antes de intentar la escritura condicional. Variables nuevas:
> `NOTIFICATIONS_BUS` (`sns` exige `NOTIFICATIONS_TOPIC_ARN`, si no `Settings` falla) y
> `NOTIFICATIONS_SCAN_SECONDS` (solo local). **DRY**: el poller del stream (`StreamReader` y el
> loop que sobrevive a la recreación de la tabla) salió de `indexer.py` a `app/streams.py`
> (`follow(db, on_records, on_attach=…)`), y lo usan el indexador y el notificador.
> En local el job **espera a que el notificador se enganche al stream** antes de su primera
> corrida: el poller arranca en `LATEST`, y una marca escrita antes no notificaría nunca. El
> evento SNS de los tests (`tests/fixtures/sns_lambda_event.json`) es el ejemplo de la
> documentación de AWS, no uno grabado en la cuenta: conviene reemplazarlo por uno real en la
> fase 7. Verificado con `docker compose up`: una reserva por la API llega a las dos bandejas en
> ~0,7 s, y una reserva vencida genera `pickup_expired` en la corrida siguiente del job (≤ 60 s).
> Para la fase 7: el notificador **lanza** ante un error (no devuelve `batchItemFailures`), así
> que el mapping necesita `bisect_batch_on_function_error`; un reintento de lote puede descontar
> dos veces un TTL, y lo absorben las defensas del contador (§5.3).

### Fase 6 — Frontend
- Reorganización del header (§7.1), campana, número rojo, panel, contexto con polling, deep links
  en «Mis reservas» y en el panel, CSS (claro y oscuro, desktop y mobile).
- **Hecho cuando**: con `ana@` y `sur@` se recorren los 6 tipos de punta a punta; el número baja al
  clickear y no al abrir; en mobile el panel no se sale de la pantalla; con la pestaña oculta no
  hay requests (verificado en la pestaña Network).

### Fase 7 — AWS
- Verificar permisos (§8.2). Módulo `notifications`, TTL en `database`, wiring en `organization`,
  `terraform-docs` del módulo.
- **Hecho cuando**: `terraform apply` desde cero levanta todo; una reserva en el ambiente
  desplegado llega a la campana; CloudWatch muestra el job cada 15 min; los logs de las tres Lambdas no tienen
  errores.

### Fase 8 — Demo y documentación
- Notificaciones de demo en el seed (§9.3) y la documentación de §14.

---

## 12. Fuera de alcance (y cómo se enchufaría)

| Qué | Cómo |
|---|---|
| **Email** | Una suscripción `email` o `email-json` al topic con filter policy por `event_type`. Para mandarle a *cada* usuario a su casilla, SNS no alcanza (una suscripción confirmada por dirección, con cuota de filter policies): lo correcto es SES, que en Learner Lab hay que verificar |
| **SMS** | `sns:Publish` con `PhoneNumber`. En el lab, SNS SMS está en sandbox: solo a números verificados |
| **Push en tiempo real** | API Gateway WebSocket + tabla de conexiones; el inbox-writer empuja después de escribir. Reemplaza al polling sin tocar la bandeja |
| **Recordatorio 24 h antes** | Otra marca (`reminder_notified_at`) y otra condición en el mismo job |
| **Notificar la extensión del plazo** | Una fila más en §4 (cambia `expires_at` con `picked_up = false`) |
| **Bandeja global para sysadmin** | `scope=library&library_id=` habilitado solo para sysadmin |
| **Idioma por usuario** | `User.language` ya existe. `messages.py` elegiría el texto por idioma |
| **Preferencias por tipo** | Ítem `PREFS` del usuario, que el inbox-writer consulta antes de escribir |
| **Analítica** | Suscripción Kinesis Data Firehose → S3, que alimenta el ETL de «Próximos pasos» del README |

---

## 13. Riesgos y trampas

- **Deriva del contador.** Cualquier camino que escriba o borre una notificación sin tocar el
  contador lo desalinea. Por eso todo pasa por `NotificationRepository`, la API recorta a ≥ 0 y
  «leer todas» lo recalcula.
- **El seed inundando las bandejas** si se olvida `origin = "seed"`, o si un día el seed pasa a
  escribir con `create` + `mark_picked_up` (generaría `MODIFY`s). Test explícito.
- **Tercer lector del stream.** Cualquier consumidor nuevo va colgado de SNS, no del stream.
- **Evento venenoso.** Sin `bisect_batch_on_function_error` y un tope de reintentos, un registro
  que rompe `detect()` congela el shard *y las notificaciones de todas las reservas*. Mismo
  cuidado que el indexador.
- **Lo que falla se pierde.** Sin cola ni destino de fallos, un evento que falla 3 veces en el
  `inbox-writer` (o un registro del stream que agota los reintentos) solo queda en los logs. Es la
  contrapartida aceptada de la simplicidad (§3.3): la reserva no se pierde, solo el aviso. Si
  hiciera falta más adelante, se suma un destino on-failure sin tocar código.
- **Latencia percibida.** Polling de 30 s más la cadena asíncrona: la notificación de lo que uno
  acaba de hacer tarda. Lo cubre `refreshSoon()`; si aun así molesta, el siguiente paso es WebSocket.
- **Vencimiento sin auto-expire.** Una reserva con el retiro vencido sigue reteniendo el ejemplar
  hasta que alguien corra «vencer reservas». El aviso a la sede lo dice, pero conviene que
  Mantenimiento muestre cuántas hay pendientes.
- **Zona horaria.** Las fechas se guardan en UTC; el texto se arma en hora de Buenos Aires. El
  frontend manda `expires_at` como fin del día local; los tests tienen que cubrir un vencimiento
  cerca de medianoche UTC.
- **Privacidad.** La notificación de la sede lleva el nombre del lector, que el librarian ya ve en
  el panel. El mensaje de SNS lleva ids, no emails ni nombres. Los logs, como en
  `cognito_triggers.py`, solo con ids.
- **Lab detenido.** Con el Learner Lab apagado no corre el job. Al volver, el primer paso avisa todo
  lo vencido en el medio: es correcto, pero llega junto.

---

## 14. Documentación a actualizar

- `README.md`: sección «Notificaciones» (eventos, campana, bandeja de sede), los 4 endpoints en la
  tabla, los servicios nuevos del compose, y la viñeta en «De este MVP a la arquitectura en AWS».
- `arquitectura-explain.md`: el topic SNS, las 3 Lambdas y la rule de EventBridge en «Componentes»;
  un «Flujo de notificaciones»; el TTL en la fila de DynamoDB.
- `docs/arquitectura.drawio.pdf`: el camino stream → notifier → SNS → inbox-writer, y
  EventBridge → scanner.
- `api/CLAUDE.md` y `api/data_base.md`: los ítems `INBOX#` y los atributos nuevos de `Reservation`.
- `api/openapi.yml`.
- `terraform/README.md` y el README del módulo (`terraform-docs`).
