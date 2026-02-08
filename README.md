# User Reminders

A Home Assistant integration that provides a _decently_ user-scoped reminder system with persistent storage and automatic scheduling. Each user gets their own reminder list that can be managed through Home Assistant services.

## Features

- **Per-user reminder lists**: Each Home Assistant user automatically gets their own reminder entity
- **Events for automation**: A background scheduler checks reminders every 30 seconds and fires events when reminders are due
- **Intents**: Intents plus a custom_sentences example handle a fair variety of ways of adding reminders.
- **Flexible due dates**: Support for dates, times, and datetime values

## User Isolation

Reminders are isolated by `user_id`. The component does it's best to verify:

- Service calls are authenticated (user context is extracted from the call)
- Users can only access/modify their own reminders
- Attempts to modify another user's reminder raise a validation error

I will note that Home Assistant wasn't exactly built for this, there may be edge cases I haven't found where service calls aren't associated with a context, or that there's a backward way of finding information from other users. So far I haven't found one, but willing to hear from users. Also note, that if your users are administrators, they can probably read anything in home assistant, and that could likely mean they could read the storage files directly, so it's not necessarily really secure.

## Installation

### Prerequisites

- Home Assistant with custom components support

### Setup

#### HACS

1. **Add to HACS**: copy this repository and paste into your HACS custom repostories.  [See the HACS FAQ for details](https://hacs.xyz/docs/faq/custom_repositories/)

   ```url
   https://github.com/qedi-r/user_reminders
   ```

#### Manual

1. Copy the `reminders` folder to your `custom_components/` directory
2. Restart Home Assistant
3. Navigate to **Settings → Devices & Services → Create Integration**
4. Search for "User Reminders"
5. Click **Create** to add the integration
6. (Optional) Select users to exclude from automatic reminder list creation

After installation, a reminder entity will be created for each non-system user in Home Assistant. Entity IDs follow the pattern: `reminder.{username}_reminders`

## Configuration

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=reminders)

### Configuration Flow

When adding the integration, you can specify which users should be **ignored** (excluded from automatic reminder entity creation). System-generated users are always ignored.

## Usage

### Services

The User Reminders integration exposes services through the parent `reminders` domain. All services accept an `entity_id` parameter pointing to a user's reminder entity, but by default the entity related to the current user will be used. If the user calling the integration doesn't match the user reminder, it will be ignored.

#### Add Reminder

Create a new reminder for the current user.
This is the **only service** that will allow automations to affect it. If you have an automation calling this service, you can use the user parameter, to add the item to that user's calendar.

**Service**: `reminders.add_item`

**Parameters**:

- `entity_id` (required): Target reminder entity (e.g., `reminders.user_reminders_glob_herman`)
- `summary` (required): Reminder text
- `due` (optional): Due date/time (ISO format or Home Assistant datetime). Defaults to tomorrow at 9:00 AM if omitted
- `user` (optional): Username (for automation-triggered calls)

**Example**:

```yaml
service: reminders.add_item
target:
  entity_id: reminders.user_reminders_glob_herman
data:
  summary: "Buy groceries"
  due: "2024-02-15T14:30:00"
```

#### Update Reminder

Modify an existing reminder.

**Service**: `reminders.update_item`

**Parameters**:

- `entity_id` (required): Target reminder entity
- `uid` (required): Reminder ID (obtained from `get_items`)
- `summary` (required): Updated reminder text
- `due` (required): Updated due date/time
- `last_fired` (optional): Timestamp when reminder was last fired (ISO format)

**Example**:

```yaml
service: reminders.update_item
target:
  entity_id: reminders.user_reminders_glob_herman
data:
  uid: "a1b2c3d4e5f6g7h8"
  summary: "Buy groceries and cook dinner"
  due: "2024-02-15T18:00:00"
```

#### Remove Reminders

Delete one or more reminders.

**Service**: `reminders.remove_item`

**Parameters**:

- `entity_id` (required): Target reminder entity
- `uids` (required): List of reminder IDs to remove

**Example**:

```yaml
service: reminders.remove_item
target:
  entity_id: reminders.user_reminders_glob_herman
data:
  uids:
    - "a1b2c3d4e5f6g7h8"
    - "i9j0k1l2m3n4o5p6"
```

#### Get Reminders

Retrieve reminders (returns response data with reminder details).

**Service**: `reminders.get_items`

**Parameters**:

- `entity_id` (required): Target reminder entity
- `uids` (optional): List of specific reminder IDs to retrieve. If omitted, returns all user's reminders

**Example**:

```yaml
service: reminders.get_items
target:
  entity_id: reminders.user_reminders_glob_herman
data:
  uids:
    - "a1b2c3d4e5f6g7h8"
```

### Automation Example

Trigger an automation when a reminder is due:

```yaml
automation:
  - alias: "Reminder Notification"
    trigger:
      platform: event
      event_type: user_reminder_due
    action:
      service: notify.mobile_app_glob_herman_phone
      data:
        message: "{{ trigger.event.data.summary }}"
```

The `user_reminder_due` event includes:

- `uid`: Reminder ID
- `summary`: Reminder text
- `due`: Due datetime (ISO format)
- `user_id`: User ID
