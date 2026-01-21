from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Window, HSplit, VSplit
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.formatted_text import to_formatted_text, FormattedText
from prompt_toolkit.widgets import Frame, TextArea
from prompt_toolkit.styles import Style
import re
from typing import List, Tuple


class FuzzyHistorySearch:
    """Fuzzy search through command history with interactive UI and match highlighting."""
    
    # Style for the search UI
    STYLE = Style.from_dict({
        'frame.border': '#888888',
        'frame.title': 'bold #8be9fd',
        'search-label': '#50fa7b bold',
        'search-input': '#f8f8f2',
        'selected': 'bg:#44475a',
        'selected-text': 'bg:#44475a #f8f8f2',
        'selected-match': 'bg:#44475a bold #50fa7b',
        'item': '#f8f8f2',
        'item-dim': '#6272a4',
        'match': 'bold #50fa7b',  # Highlighted matching characters
        'no-match': '#ff5555 italic',
        'counter': '#6272a4',
        'hint': '#6272a4 italic',
    })
    
    def __init__(self, history_strings: list[str]):
        # Deduplicate and reverse history (newest first)
        seen = set()
        self.history = []
        for cmd in reversed(history_strings):
            if cmd and cmd.strip() and cmd not in seen:
                self.history.append(cmd)
                seen.add(cmd)
        
        self.filtered_history = self.history[:]
        self.selected_index = 0
        self._current_query = ""
        self.search_buffer = Buffer(
            multiline=False, 
            on_text_changed=self._on_search_changed
        )

    def _on_search_changed(self, _):
        """Filter history based on search query."""
        query = self.search_buffer.text.lower().strip()
        self._current_query = query
        self.selected_index = 0
        
        if not query:
            self.filtered_history = self.history[:]
            return

        # Simple fuzzy match: characters must appear in order
        try:
            pattern = ".*".join(map(re.escape, query))
            regex = re.compile(pattern, re.IGNORECASE)
            self.filtered_history = [
                cmd for cmd in self.history 
                if regex.search(cmd)
            ]
        except re.error:
            # Fallback to simple containment if regex fails
            self.filtered_history = [
                cmd for cmd in self.history 
                if query in cmd.lower()
            ]

    def _highlight_matches(self, text: str, query: str, is_selected: bool) -> List[Tuple[str, str]]:
        """Highlight matching characters in text.
        
        Returns a list of (style, text) tuples for FormattedText.
        """
        if not query:
            style = 'class:selected-text' if is_selected else 'class:item'
            return [(style, text)]
        
        result = []
        text_lower = text.lower()
        query_lower = query.lower()
        
        # Find positions of matching characters (fuzzy match)
        match_positions = set()
        query_idx = 0
        
        for i, char in enumerate(text_lower):
            if query_idx < len(query_lower) and char == query_lower[query_idx]:
                match_positions.add(i)
                query_idx += 1
        
        # Build formatted text with highlights
        current_text = ""
        current_is_match = False
        
        base_style = 'class:selected-text' if is_selected else 'class:item'
        match_style = 'class:selected-match' if is_selected else 'class:match'
        
        for i, char in enumerate(text):
            is_match = i in match_positions
            
            if is_match != current_is_match and current_text:
                # Style changed, flush current segment
                style = match_style if current_is_match else base_style
                result.append((style, current_text))
                current_text = ""
            
            current_text += char
            current_is_match = is_match
        
        # Flush remaining text
        if current_text:
            style = match_style if current_is_match else base_style
            result.append((style, current_text))
        
        return result

    def _get_content(self):
        """Render the list of commands with highlighted matches."""
        result = []
        max_visible = 12
        max_width = 80
        
        # Calculate visible window
        start_idx = 0
        if self.selected_index >= max_visible:
            start_idx = self.selected_index - max_visible + 1
        
        visible_items = self.filtered_history[start_idx:start_idx + max_visible]
        
        for i, item in enumerate(visible_items):
            actual_idx = start_idx + i
            is_selected = actual_idx == self.selected_index
            
            # Truncate long commands
            display_item = item if len(item) <= max_width else item[:max_width - 3] + "..."
            
            # Add prefix
            if is_selected:
                result.append(('class:selected', ' > '))
            else:
                result.append(('class:item-dim', '   '))
            
            # Add highlighted text
            highlighted = self._highlight_matches(display_item, self._current_query, is_selected)
            result.extend(highlighted)
            
            result.append(('', '\n'))
        
        if not visible_items:
            result.append(('class:no-match', '   No matches found'))
            result.append(('', '\n'))
        
        # Remove trailing newline
        if result and result[-1] == ('', '\n'):
            result.pop()
            
        return result

    def _get_header(self):
        """Render the header with search label and counter."""
        total = len(self.history)
        filtered = len(self.filtered_history)
        
        return [
            ('class:search-label', ' 🔍 '),
            ('class:counter', f'({filtered}/{total}) '),
            ('class:hint', '↑↓ navigate  Enter select  Esc cancel'),
        ]

    async def run_async(self):
        """Run the search UI and return selected command or None."""
        if not self.history:
            return None
            
        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("escape")
        @kb.add("c-g")
        def cancel(event):
            event.app.exit(result=None)

        @kb.add("enter")
        @kb.add("c-m")
        def select(event):
            if self.filtered_history:
                event.app.exit(result=self.filtered_history[self.selected_index])
            else:
                event.app.exit(result=None)

        @kb.add("up")
        @kb.add("c-p")
        def move_up(event):
            if self.filtered_history:
                self.selected_index = max(0, self.selected_index - 1)

        @kb.add("down")
        @kb.add("c-n")
        def move_down(event):
            if self.filtered_history:
                max_idx = len(self.filtered_history) - 1
                self.selected_index = min(max_idx, self.selected_index + 1)
        
        @kb.add("pageup")
        def page_up(event):
            if self.filtered_history:
                self.selected_index = max(0, self.selected_index - 10)
        
        @kb.add("pagedown")
        def page_down(event):
            if self.filtered_history:
                max_idx = len(self.filtered_history) - 1
                self.selected_index = min(max_idx, self.selected_index + 10)
        
        @kb.add("home")
        def go_home(event):
            self.selected_index = 0
        
        @kb.add("end")
        def go_end(event):
            if self.filtered_history:
                self.selected_index = len(self.filtered_history) - 1
        
        @kb.add("c-u")  # Clear search input
        def clear_input(event):
            self.search_buffer.text = ""

        # Layout components
        header = Window(
            content=FormattedTextControl(text=self._get_header),
            height=1
        )
        
        search_field = Window(
            content=BufferControl(buffer=self.search_buffer),
            height=1
        )
        
        separator = Window(height=1, char="─", style="class:frame.border")
        
        list_view = Window(
            content=FormattedTextControl(text=self._get_content),
            height=Dimension(min=3, max=14)
        )
        
        root_container = Frame(
            HSplit([
                header,
                search_field,
                separator,
                list_view
            ]),
            title=" History Search ",
            style="class:frame.border"
        )

        app = Application(
            layout=Layout(root_container, focused_element=search_field),
            key_bindings=kb,
            style=self.STYLE,
            full_screen=False,
            mouse_support=True
        )

        return await app.run_async()
