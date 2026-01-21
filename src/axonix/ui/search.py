from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Window, HSplit
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.widgets import Frame
import re

class FuzzyHistorySearch:
    def __init__(self, history_strings: list[str]):
        # Deduplicate and reverse history (newest first)
        seen = set()
        self.history = []
        for cmd in reversed(history_strings):
            if cmd and cmd not in seen:
                self.history.append(cmd)
                seen.add(cmd)
        
        self.filtered_history = self.history[:]
        self.selected_index = 0
        self.search_buffer = Buffer(multiline=False, on_text_changed=self._on_search_changed)

    def _on_search_changed(self, _):
        """Filter history based on search query."""
        query = self.search_buffer.text.lower()
        self.selected_index = 0
        
        if not query:
            self.filtered_history = self.history[:]
            return

        # Simple fuzzy match: characters must appear in order
        # e.g. "git" matches "g..i..t.."
        # Regex: .*g.*i.*t.*
        try:
            pattern = ".*".join(map(re.escape, query))
            regex = re.compile(pattern)
            self.filtered_history = [
                cmd for cmd in self.history 
                if regex.search(cmd.lower())
            ]
        except Exception:
            # Fallback to simple containment if regex fails
            self.filtered_history = [
                cmd for cmd in self.history 
                if query in cmd.lower()
            ]

    def _get_content(self):
        """Render the list of commands."""
        result = []
        height = 15  # Max items to show
        
        start_idx = 0
        # Scroll logic
        if self.selected_index > height - 1:
            start_idx = self.selected_index - (height - 1)
        
        visible_items = self.filtered_history[start_idx : start_idx + height]
        
        for i, item in enumerate(visible_items):
            actual_idx = start_idx + i
            if actual_idx == self.selected_index:
                # Highlight selected
                result.append([("class:reverse", f"> {item}")])
            else:
                result.append([("", f"  {item}")])
            result.append([("", "\n")])
            
        if not visible_items:
            result.append([("class:error", "  No matches found")])
            
        return to_formatted_text([frag for line in result for frag in line])

    async def run_async(self):
        """Run the search UI and return selected command or None."""
        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("escape")
        def _(event):
            event.app.exit(result=None)

        @kb.add("enter")
        def _(event):
            if self.filtered_history:
                event.app.exit(result=self.filtered_history[self.selected_index])
            else:
                event.app.exit(result=None)

        @kb.add("up")
        def _(event):
            self.selected_index = max(0, self.selected_index - 1)

        @kb.add("down")
        def _(event):
            max_idx = max(0, len(self.filtered_history) - 1)
            self.selected_index = min(max_idx, self.selected_index + 1)
            
        @kb.add("tab") # Also allow tab to select
        def _(event):
            if self.filtered_history:
                event.app.exit(result=self.filtered_history[self.selected_index])

        # Layout
        search_field = Window(
            content=BufferControl(buffer=self.search_buffer),
            height=Dimension(min=1, max=1),
            char=" "
        )
        
        list_view = Window(
            content=FormattedTextControl(text=self._get_content),
            height=Dimension(min=5, max=15)
        )
        
        root_container = Frame(
            HSplit([
                Window(FormattedTextControl("Search History (Fuzzy):"), height=1),
                search_field,
                Window(height=1, char="-"),
                list_view
            ]),
            title="History Search"
        )

        app = Application(
            layout=Layout(root_container, focused_element=search_field),
            key_bindings=kb,
            full_screen=False,
            mouse_support=True
        )

        return await app.run_async()
