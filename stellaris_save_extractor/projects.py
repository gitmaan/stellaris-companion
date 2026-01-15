from __future__ import annotations

import re


class ProjectsMixin:
    """Extractors for special projects, event chains, and precursor progress."""

    # Known precursor chain identifiers
    PRECURSOR_CHAINS = {
        'yuht': 'Yuhtaan (First Colonizers)',
        'first_league': 'First League',
        'cybrex': 'Cybrex (Ancient Machines)',
        'irassian': 'Irassian Concordat',
        'vultaum': 'Vultaum Star Assembly',
        'zroni': 'Zroni (Psionic Precursors)',
    }

    # Notable event chains worth tracking
    NOTABLE_CHAINS = {
        'horizon_signal': 'Horizon Signal (The Worm)',
        'ghost_signal': 'Ghost Signal (Contingency warning)',
        'ai_crisis': 'AI Crisis',
        'war_in_heaven': 'War in Heaven',
        'prethoryn': 'Prethoryn Scourge',
        'extradimensional': 'Extradimensional Invaders',
        'gray': 'Gray (L-Cluster)',
        'market_founding': 'Galactic Market Founding',
        'wenkwort': 'Wenkwort Artem',
        'shroud': 'Shroud Events',
    }

    def get_special_projects(self) -> dict:
        """Get special projects, event chains, and precursor progress.

        Returns:
            Dict with:
              - active_projects: List of active special projects with days_left
              - active_count: Number of pending projects
              - soonest_completion: Days until next project completes
              - completed_chains: List of completed event chain names
              - notable_completed: Human-readable notable completions
              - precursor_progress: Dict of precursor chain status
        """
        result = {
            'active_projects': [],
            'active_count': 0,
            'soonest_completion': None,
            'completed_chains': [],
            'notable_completed': [],
            'precursor_progress': {},
        }

        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)

        if not player_chunk:
            return result

        # Extract active special projects
        active_projects = self._extract_active_projects(player_chunk)
        result['active_projects'] = active_projects
        result['active_count'] = len(active_projects)

        if active_projects:
            days_list = [p['days_left'] for p in active_projects if p.get('days_left')]
            if days_list:
                result['soonest_completion'] = min(days_list)

        # Extract completed event chains
        completed_chains = self._extract_completed_chains(player_chunk)
        result['completed_chains'] = completed_chains

        # Identify notable completed chains
        notable = []
        for chain in completed_chains:
            chain_lower = chain.lower()
            for key, name in self.NOTABLE_CHAINS.items():
                if key in chain_lower:
                    notable.append(name)
                    break
        result['notable_completed'] = list(set(notable))

        # Extract precursor progress
        precursor_progress = self._extract_precursor_progress(player_chunk)
        result['precursor_progress'] = precursor_progress

        return result

    def _extract_active_projects(self, player_chunk: str) -> list[dict]:
        """Extract active special projects from player's events section."""
        projects = []

        # Find the events section
        events_block = self._extract_braced_block(player_chunk, 'events')
        if not events_block:
            return projects

        # Find all special_project blocks
        for match in re.finditer(r'\bspecial_project\s*=\s*\{', events_block):
            start = match.start()

            # Extract the block
            brace_count = 0
            end = None
            for i, char in enumerate(events_block[start:], start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break

            if end is None:
                continue

            block = events_block[start:end]

            project = {}

            # Extract project ID
            id_match = re.search(r'\bid=(\d+)', block)
            if id_match:
                project['id'] = int(id_match.group(1))

            # Extract days left
            days_match = re.search(r'\bdays_left=(\d+)', block)
            if days_match:
                project['days_left'] = int(days_match.group(1))

            # Extract debris/coordinate reference (links to what's being investigated)
            debris_match = re.search(r'\bdebris=(\d+)', block)
            if debris_match:
                project['debris_id'] = int(debris_match.group(1))

            if project:
                projects.append(project)

        return projects

    def _extract_completed_chains(self, player_chunk: str) -> list[str]:
        """Extract completed event chain names."""
        chains = []

        # Find all completed_event_chain entries
        for match in re.finditer(r'\bcompleted_event_chain\s*=\s*"([^"]+)"', player_chunk):
            chain_name = match.group(1)
            if chain_name and chain_name not in chains:
                chains.append(chain_name)

        return chains

    def _extract_precursor_progress(self, player_chunk: str) -> dict:
        """Extract precursor chain progress from player country data."""
        progress = {}

        for precursor_key, precursor_name in self.PRECURSOR_CHAINS.items():
            precursor_data = self._check_precursor(player_chunk, precursor_key)
            if precursor_data['found']:
                progress[precursor_key] = {
                    'name': precursor_name,
                    **precursor_data
                }

        return progress

    def _check_precursor(self, player_chunk: str, precursor: str) -> dict:
        """Check progress on a specific precursor chain."""
        result = {
            'found': False,
            'stage': 'not_started',
            'homeworld_found': False,
            'artifacts': 0,
        }

        # Check for intro (chain started)
        intro_pattern = rf'\b{precursor}_intro=(\d+)'
        if re.search(intro_pattern, player_chunk):
            result['found'] = True
            result['stage'] = 'started'

        # Check for various stage markers
        stage_patterns = [
            (rf'\b{precursor}_world_found=', 'homeworld_found'),
            (rf'\b{precursor}_homeworld=', 'homeworld_found'),
            (rf'\b{precursor}_system=', 'system_located'),
        ]

        for pattern, stage in stage_patterns:
            if re.search(pattern, player_chunk):
                result['found'] = True
                result['stage'] = stage
                if 'homeworld' in stage or 'world' in stage:
                    result['homeworld_found'] = True

        # Count artifact-related entries (numbered stages like yuht_2, yuht_6)
        artifact_pattern = rf'\b{precursor}_(\d+)='
        artifacts = re.findall(artifact_pattern, player_chunk)
        if artifacts:
            result['found'] = True
            result['artifacts'] = len(set(artifacts))
            if result['stage'] == 'not_started':
                result['stage'] = 'collecting_artifacts'

        # Check completed chains for this precursor
        chain_pattern = rf'{precursor}.*chain'
        if re.search(chain_pattern, player_chunk, re.IGNORECASE):
            # Look specifically in completed_event_chain entries
            completed_pattern = rf'completed_event_chain\s*=\s*"[^"]*{precursor}[^"]*homeworld[^"]*"'
            if re.search(completed_pattern, player_chunk, re.IGNORECASE):
                result['found'] = True
                result['stage'] = 'completed'
                result['homeworld_found'] = True

        return result

    def get_event_chains(self) -> dict:
        """Get a summary of event chain progress (simpler view).

        Returns:
            Dict with completed chain names and notable story events.
        """
        projects = self.get_special_projects()
        return {
            'completed_chains': projects['completed_chains'],
            'notable_completed': projects['notable_completed'],
            'precursors': projects['precursor_progress'],
        }
