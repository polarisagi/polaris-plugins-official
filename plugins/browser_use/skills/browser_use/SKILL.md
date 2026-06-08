---
name: browser_use
description: "Standard operating procedure for the browser MCP tool utilizing DOM-based automation."
version: "1.0.0"
tags:
  - browser-use
  - automation
  - web
exec_mode: ambient
risk_level: medium
sandbox: L2
capability: read-write
---

## 1. Operating Paradigm
You are controlling a web browser. You MUST rely on structural DOM extraction rather than raw visual coordinate estimation.

## 2. Standard Workflow
1. **Navigation**: Use `navigate` to load the target URL.
2. **Inspection**: Use `get_interactive_dom` to extract all visible interactive elements (each assigned a unique `polaris-id`). To read the overall text of a page (e.g., an article), use `get_page_content` instead. To check your current URL, use `get_current_state`.
3. **Interaction**: Use `action_by_id` with the corresponding `polaris-id` to execute clicks, hovers, or text inputs. NEVER use raw `[x, y]` coordinates.
4. **Tab Management**: If you open a link that spawns a new tab, you can read it and then use `close_tab` to return to your previous work. Use `go_back` for standard history navigation.
5. **Verification**: Call `get_interactive_dom` after critical interactions (e.g., form submissions, page transitions) to confirm the new state before proceeding.

## 3. Navigation & Interaction Rules
- **Scrolling**: Elements outside the current viewport may not appear in the DOM dump. Use `scroll_page` to navigate vertically, then re-call `get_interactive_dom`.
- **Overlays & Modals**: Actively check the DOM for cookie consent banners, ads, or blocking overlays. Identify their `polaris-id` and close them before attempting to interact with underlying content.

## 4. Error Recovery & Safety
- **Missing Targets**: If an expected element is missing, do not guess IDs. Scroll the page or re-fetch the DOM.
- **Sensitive Operations**: Require explicit human confirmation before executing critical actions via `action_by_id` (e.g., submitting payments, making destructive configuration changes).
