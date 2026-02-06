/**
 * User Reminders Card
 *
 * A custom Lovelace card that displays reminders for the currently logged-in user.
 * Automatically detects the user and subscribes to real-time updates.
 */

import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@2.0.1/lit-element.js?module";

class UserRemindersCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      config: { type: Object },
      _reminders: { type: Array },
      _loading: { type: Boolean },
      _error: { type: String },
      _entityId: { type: String },
      _editingReminder: { type: Object },
      _editSummary: { type: String },
      _editDue: { type: String },
    };
  }

  static getConfigElement() {
    return document.createElement("user-reminders-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  constructor() {
    super();
    this._reminders = [];
    this._loading = true;
    this._error = null;
    this._entityId = null;
    this._unsubscribe = null;
    this._refreshInterval = null;
    this._editingReminder = null;
    this._editSummary = "";
    this._editDue = "";
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    this.config = config;
  }

  checkIfEntityStateChanged(oldState) {
    const newState = this._hass?.states[this._entityId];
    if (oldState && newState) {
      if (
        oldState.state !== newState?.state ||
        oldState.last_changed !== newState?.last_changed
      ) {
        this._loadReminders();
      }
    }
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;

    if (!oldHass || oldHass.user?.id !== hass.user?.id) {
      this._determineEntityId();
      this._loadReminders();
      return;
    }

    this.checkIfEntityStateChanged(oldHass?.states?.[this._entityId]);
  }

  shouldUseConfiguredEntityId() {
    return this.config.entity_id;
  }

  expectedEntityIdForUser(userName) {
    const slugify = (str) =>
      str
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "_")
        .replace(/_+/g, "_");
    const userSlug = slugify(userName);
    return `reminders.user_reminders_${userSlug}`;
  }

  _determineEntityId() {
    if (!this._hass?.user) {
      this._error = "User information not available";
      return;
    }

    const userName = this._hass.user.name;

    if (this.shouldUseConfiguredEntityId()) {
      this._entityId = this.config.entity_id;
      console.debug(
        `[User Reminders] Using configured entity_id: ${this._entityId}`,
      );
      this._startRefreshInterval();
      return;
    }

    const expectedEntityId = this.expectedEntityIdForUser(userName);
    if (this._hass.states[expectedEntityId]) {
      this._entityId = expectedEntityId;
      console.debug(
        `[User Reminders] Auto-detected entity_id: ${this._entityId}`,
      );
      this._startRefreshInterval();
      return;
    }

    this._error = `Could not find reminder entity for user ${userName}`;
    console.error(`[User Reminders] ${this._error}`);
  }

  async _loadReminders() {
    if (!this._entityId) {
      this._loading = false;
      return;
    }

    this._loading = true;
    this._error = null;

    try {
      const service_parameters = {};
      const service_target = { entity_id: this._entityId };
      const response = await this._hass.callService(
        "reminders",
        "get_items",
        service_parameters,
        service_target,
        false,
        true,
      );

      this._reminders = response.response[this._entityId]?.reminders || [];
      console.debug(
        `[User Reminders] Loaded ${this._reminders.length} reminders`,
      );
      this._loading = false;
      this.requestUpdate();
    } catch (err) {
      console.error("[User Reminders] Failed to load reminders:", err);
      this._error = `Failed to load reminders: ${err.message}`;
      this._loading = false;
      this.requestUpdate();
    }
  }

  _startRefreshInterval() {
    if (this._refreshInterval) {
      return;
    }
    this._refreshInterval = setInterval(() => {
      this._loadReminders();
    }, 120000);
  }

  async _deleteReminder(reminderId) {
    if (!this._entityId) {
      return;
    }

    try {
      await this._hass.callService(
        "reminders",
        "remove_item",
        { uids: [reminderId] },
        { entity_id: this._entityId },
        false,
        false,
      );
      console.debug(`[User Reminders] Deleted reminder ${reminderId}`);
      await this._loadReminders();
    } catch (err) {
      console.error("[User Reminders] Failed to delete reminder:", err);
      this._error = `Failed to delete reminder: ${err.message}`;
      this.requestUpdate();
    }
  }

  _openEditDialog(reminder) {
    this._editingReminder = reminder;
    this._editSummary = reminder.summary;
    // Convert ISO string to datetime-local format (YYYY-MM-DDTHH:MM+ZZ)
    const due = new Date(reminder.due);
    const pad = (n) => String(n).padStart(2, "0");
    this._editDue = `${due.getFullYear()}-${pad(due.getMonth() + 1)}-${pad(due.getDate())}T${pad(due.getHours())}:${pad(due.getMinutes())}`;
    this.requestUpdate();
  }

  _closeEditDialog() {
    this._editingReminder = null;
    this._editSummary = "";
    this._editDue = "";
    this.requestUpdate();
  }

  async _saveEdit() {
    if (!this._editingReminder || !this._entityId) {
      return;
    }

    const dueDate = new Date(this._editDue);
    const dueIso = dueDate.toISOString();

    try {
      await this._hass.callService(
        "reminders",
        "update_item",
        {
          uid: this._editingReminder.id,
          summary: this._editSummary,
          due: dueIso,
        },
        { entity_id: this._entityId },
        false,
        false,
      );
      console.debug(
        `[User Reminders] Updated reminder ${this._editingReminder.id}`,
      );
      this._closeEditDialog();
      await this._loadReminders();
    } catch (err) {
      console.error("[User Reminders] Failed to update reminder:", err);
      this._error = `Failed to update reminder: ${err.message}`;
      this._closeEditDialog();
      this.requestUpdate();
    }
  }

  _isToday(due, now) {
    return due.toDateString() === now.toDateString();
  }

  _today_at(due) {
    const timeStr = due.toLocaleTimeString(this._hass.language, {
      hour: "2-digit",
      minute: "2-digit",
    });
    return `Today at ${timeStr}`;
  }

  _isTomorrow(due, now) {
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    return due.toDateString() === tomorrow.toDateString();
  }

  _tomorrow_at(due) {
    const timeStr = due.toLocaleTimeString(this._hass.language, {
      hour: "2-digit",
      minute: "2-digit",
    });
    return `Tomorrow at ${timeStr}`;
  }

  _isWithin7Days(due, now) {
    const diffMs = due - now;
    const diffHours = diffMs / (1000 * 60 * 60);
    return diffHours > 0 && diffHours < 168;
  }

  _dayName_at_time(due) {
    const dayName = due.toLocaleDateString(this._hass.language, {
      weekday: "long",
    });
    const timeStr = due.toLocaleTimeString(this._hass.language, {
      hour: "2-digit",
      minute: "2-digit",
    });
    return `${dayName} at ${timeStr}`;
  }

  _full_date(due) {
    return due.toLocaleDateString(this._hass.language, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  _formatDue(dueStr) {
    try {
      const due = new Date(dueStr);
      const now = new Date();

      if (this._isToday(due, now)) {
        return this._today_at(due);
      } else if (this._isTomorrow(due, now)) {
        return this._tomorrow_at(due);
      } else if (this._isWithin7Days(due, now)) {
        return this._dayName_at_time(due);
      } else {
        return this._full_date(due);
      }
    } catch (err) {
      return dueStr;
    }
  }

  _isOverdue(dueStr) {
    try {
      const due = new Date(dueStr);
      return due < new Date();
    } catch {
      return false;
    }
  }

  render() {
    if (this._loading) {
      return html`
        <ha-card header="Reminders">
          <div class="loading">
            <ha-circular-progress active></ha-circular-progress>
          </div>
        </ha-card>
      `;
    }

    if (this._error) {
      return html`
        <ha-card header="Reminders">
          <div class="error">
            <ha-icon icon="mdi:alert-circle"></ha-icon>
            <span>${this._error}</span>
          </div>
        </ha-card>
      `;
    }

    if (this._reminders.length === 0) {
      return html`
        <ha-card header="Reminders">
          <div class="empty">
            <ha-icon icon="mdi:check-circle-outline"></ha-icon>
            <span>No upcoming reminders</span>
          </div>
        </ha-card>
      `;
    }

    const sortedReminders = [...this._reminders].sort((a, b) => {
      return new Date(a.due) - new Date(b.due);
    });

    return html`
      <ha-card header="Reminders">
        <div class="reminder-list">
          ${sortedReminders.map(
            (reminder) => html`
              <div
                class="reminder-item ${this._isOverdue(reminder.due)
                  ? "overdue"
                  : ""}"
              >
                <div
                  class="reminder-content clickable"
                  @click=${() => this._openEditDialog(reminder)}
                >
                  <div class="reminder-summary">${reminder.summary}</div>
                  <div class="reminder-due">
                    <ha-icon
                      icon="${this._isOverdue(reminder.due)
                        ? "mdi:clock-alert"
                        : "mdi:clock-outline"}"
                    ></ha-icon>
                    ${this._formatDue(reminder.due)}
                  </div>
                </div>
                <ha-icon-button
                  @click=${() => {
                    this._deleteReminder(reminder.id);
                  }}
                  class="delete-button"
                  title="Mark as done"
                ><slot><ha-icon icon="mdi:check-circle-outline"></ha-icon></slot></ha-icon-button>
              </div>
            `,
          )}
        </div>
      </ha-card>
      ${this._editingReminder
        ? html`
            <div class="edit-overlay" @click=${() => this._closeEditDialog()}>
              <div class="edit-dialog" @click=${(e) => e.stopPropagation()}>
                <div class="edit-header">
                  <span>Edit Reminder</span>
                  <ha-icon-button
                    @click=${() => this._closeEditDialog()}
                  >
                    <slot><ha-icon icon="mdi:close"></ha-icon></slot>
                  </ha-icon-button>
                </div>
                <div class="edit-body">
                  <label class="edit-label">
                    Summary
                    <input
                      type="text"
                      class="edit-input"
                      .value=${this._editSummary}
                      @input=${(e) => {
                        this._editSummary = e.target.value;
                      }}
                    />
                  </label>
                  <label class="edit-label">
                    Due
                    <input
                      type="datetime-local"
                      class="edit-input"
                      .value=${this._editDue}
                      @input=${(e) => {
                        this._editDue = e.target.value;
                      }}
                    />
                  </label>
                </div>
                <div class="edit-actions">
                  <button
                    class="edit-btn edit-btn-cancel"
                    @click=${() => this._closeEditDialog()}
                  >
                    Cancel
                  </button>
                  <button
                    class="edit-btn edit-btn-save"
                    @click=${() => this._saveEdit()}
                  >
                    Save
                  </button>
                </div>
              </div>
            </div>
          `
        : ""}
    `;
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }

      ha-card {
        padding: 16px;
      }

      .loading,
      .error,
      .empty {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 24px;
        gap: 12px;
      }

      .error {
        color: var(--error-color);
      }

      .empty {
        color: var(--secondary-text-color);
      }

      .reminder-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .reminder-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px;
        background: var(--card-background-color);
        border-radius: 8px;
        border-left: 4px solid var(--primary-color);
        transition: all 0.2s;
      }

      .reminder-item:hover {
        background: var(--secondary-background-color);
        transform: translateX(4px);
      }

      .delete-button {
        --mdc-icon-button-size: 36px;
        color: var(--primary-color);
      }

      .delete-button:hover {
        color: var(--success-color, #4caf50);
      }

      .reminder-item.overdue {
        border-left-color: var(--error-color);
        background: var(--error-color-transparent, rgba(244, 67, 54, 0.1));
      }

      .reminder-content {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .reminder-summary {
        font-weight: 500;
        font-size: 14px;
      }

      .reminder-due {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .reminder-item.overdue .reminder-due {
        color: var(--error-color);
      }

      ha-icon {
        --mdc-icon-size: 18px;
      }

      .clickable {
        cursor: pointer;
      }

      .edit-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 999;
      }

      .edit-dialog {
        background: var(--card-background-color, #fff);
        border-radius: 12px;
        padding: 0;
        width: 90%;
        max-width: 400px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        overflow: hidden;
      }

      .edit-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 8px 16px 20px;
        font-size: 18px;
        font-weight: 500;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }

      .edit-body {
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 16px;
      }

      .edit-label {
        display: flex;
        flex-direction: column;
        gap: 6px;
        font-size: 13px;
        font-weight: 500;
        color: var(--secondary-text-color);
      }

      .edit-input {
        padding: 10px 12px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 8px;
        font-size: 14px;
        font-family: inherit;
        background: var(--primary-background-color, #fafafa);
        color: var(--primary-text-color);
        outline: none;
        transition: border-color 0.2s;
      }

      .edit-input:focus {
        border-color: var(--primary-color);
      }

      .edit-actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        padding: 12px 20px 16px;
      }

      .edit-btn {
        padding: 8px 20px;
        border-radius: 8px;
        border: none;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: background 0.2s;
      }

      .edit-btn-cancel {
        background: transparent;
        color: var(--secondary-text-color);
      }

      .edit-btn-cancel:hover {
        background: var(--secondary-background-color, #f0f0f0);
      }

      .edit-btn-save {
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
      }

      .edit-btn-save:hover {
        opacity: 0.9;
      }
    `;
  }

  getCardSize() {
    const baseSize = 2;
    const itemSize = this._reminders.length * 1.2;
    return Math.max(baseSize + itemSize, 3);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsubscribe) {
      this._unsubscribe();
    }
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
  }
}

customElements.define("user-reminders-card", UserRemindersCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "user-reminders-card",
  name: "User Reminders",
  description: "Display reminders for the currently logged-in user",
  preview: false,
});
