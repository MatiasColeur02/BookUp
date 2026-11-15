import { fullDate, styleOf, timeAgo } from "../lib/notifications";
import type { Notification } from "../types";

interface Props {
  notification: Notification;
  onOpen: (notification: Notification) => void;
}

/** Una notificación: ícono por tipo, título, cuerpo y hace cuánto. Resaltada si no se leyó. */
export function NotificationItem({ notification, onOpen }: Props) {
  const { tone, Icon } = styleOf(notification.type);
  const unread = notification.read_at === null;

  return (
    <li>
      <button
        type="button"
        className={`notif-item${unread ? " is-unread" : ""}`}
        onClick={() => onOpen(notification)}
      >
        <span className={`notif-icon notif-tone-${tone}`} aria-hidden="true">
          <Icon />
        </span>
        <span className="notif-text">
          <span className="notif-head">
            <span className="notif-title">
              {unread && <span className="visually-hidden">Sin leer: </span>}
              {notification.title}
            </span>
            <time className="notif-time" dateTime={notification.created_at} title={fullDate(notification.created_at)}>
              {timeAgo(notification.created_at)}
            </time>
          </span>
          <span className="notif-body">{notification.body}</span>
        </span>
        {unread && <span className="notif-dot" aria-hidden="true" />}
      </button>
    </li>
  );
}
