Note: this documentation might not be up-to-date. If you notice outdated references, please update them

----------------------------------
# Command Activity
Command Activity (or activity) is a way to manage a state for longer than a single message. While basic commands are "_request scoped_" in a sense that no state is persisted between commands other than in database. Activities are "_chat scoped_" as in Activity is persisted in memory in a scope of a single Telegram chat. This way intermediate state changes can be stored between commands and/or messages. This enables usage of Telegrams [inline keyboards](https://core.telegram.org/bots/2-0-intro).

Single activity can be started by any action. Activity consists of one or more states. States determine behavior of the bot. Thus this is an implementation of [state pattern](https://refactoring.guru/design-patterns/state). Activity itself is a wrapper object that is stored in the command service instance.

`command_activity.py` defines class that can be inherited to define more granular behavior or to have additional state in it by storing data in activity variables. Command Activity can be used as it is as it defines basic interface for managing an activity.

- `__init__`: First state of the activity should be given as a parameter. If state is given it is executed immediately. `host_message` is bots message that "contains" the activity. That way replies to the host message or callback queries (from inline keyboard buttons) are delegated to the current state of the activity.
- `delegate_response`: method that receives users reply to `host_message` and delgates it to the current state. If update has `callback_query` it is passed to the state as is. If it is normal reply, current states `preprocess_reply_data` method is called first. State might not implement `preprocess_reply_data` and in that case the callback_query data is passed as is.
- `change_state`: changes activity's state to given state and executes that state immediately
- `update_host_message_content`: updates activity's host message text and/or `InlineKeyboardMarkup`
- `done`: ends activity, removes keyboard and removes activity from command services activity storage

### Examples 
- using CommandActivity as is, check `DailyQuestionCommand`
- inheriting CommandActivity and extending it, check `StartSeasonActivity`

## Activity states
Activity state is a "step" of activity that defines how bot should behave in that stage/step of the activity. State has reference to its activity through which it can proceed action to next state. Single state has no knowledge of its preceding state and as such states can be though to be a linked list of steps for activity. `ActivityState` is interface for concrete implementations of different activity states and cannot be used as is.

Activity state can have its own state, it can store state in CommandActivity, or it can pass all intermediate data to the next state.

- `execute_state`: executes the state. Can do anything, but normal behavior is to update host messages content and/or keyboard.
- `preprocess_reply_data`: if implemented, preprocesses users messages text content that is then passed to the `handle_response`
- `handle_response`: handles users message reply or callback_query data

### Examples
- concrete implementation of activity state, check `DQMainMenuState`
- extending state to activity specific base class, check `StartSeasonActivityState`