from supabase import create_client
import flet as ft
from pages.config import SUPABASE_CONFIG, TABLE_NAME, PAGE_SIZE
import threading
import requests
import time

class DataViewerApp:
    def __init__(self):
        self.init_supabase_client()
        self.page_size = PAGE_SIZE
        self.current_page = 0
        self.total_records = 0
        self.filtered_records = 0
        self.min_search_length = 3  # Minimum de caractères pour la recherche
        # Ajouter une variable pour gérer les délais
        self.debounce_timer = None
        self.max_retries = 3
        self.retry_delay = 1  # secondes

    def init_supabase_client(self):
        """Initialize Supabase client with retry mechanism"""
        try:
            self.supabase = create_client(
                SUPABASE_CONFIG["url"],
                SUPABASE_CONFIG["key"]
            )
        except Exception as e:
            print(f"Error initializing Supabase client: {e}")
            raise

    def execute_with_retry(self, query_func):
        """Execute a query with retry mechanism"""
        retries = 0
        while retries < self.max_retries:
            try:
                return query_func()
            except Exception as e:
                retries += 1
                if "Server disconnected" in str(e) or "WinError 10054" in str(e):
                    if retries < self.max_retries:
                        print(f"Connection lost, retrying ({retries}/{self.max_retries})...")
                        time.sleep(self.retry_delay)
                        # Reinitialize client before retry
                        self.init_supabase_client()
                    else:
                        print(f"Max retries reached. Last error: {e}")
                        raise
                else:
                    print(f"Unexpected error: {e}")
                    raise

    def update_value(self, edge_of_odds_field, increment):
        try:
            current_value = float(edge_of_odds_field.value) if edge_of_odds_field.value else 0
        except ValueError:
            current_value = 0

        new_value = current_value + increment

        if 0 <= new_value <= 0.5:
            edge_of_odds_field.value = f"{new_value:.2f}"
            edge_of_odds_field.update()

            # Annuler tout appel de recherche précédent en cours
            if self.debounce_timer:
                self.debounce_timer.cancel()

            # Démarrer un nouvel appel avec un délai (par exemple, 300 ms)
            self.debounce_timer = threading.Timer(0.3, self.search_data, [None])
            self.debounce_timer.start()

    def get_total_count(self):
        def query_func():
            return self.supabase.from_(TABLE_NAME).select('*', count='exact').execute()
        try:
            result = self.execute_with_retry(query_func)
            return result.count
        except Exception as e:
            print(f"Erreur lors du comptage total: {e}")
            return 0

    def load_leagues(self):
        def query_func():
            return self.supabase.table(TABLE_NAME).select("LEAGUE").execute()
        try:
            # Charger toutes les ligues depuis la base de données
            response = self.execute_with_retry(query_func)
            
            # Définir les ligues favorites
            favorite_leagues = ["Eng1", "Spa1", "Spa2", "Spa", "Ger1", "Ita1", "Fra1", "Ned1", "Mar1", "Ita", "Por1"]

            # Définir les ligues Importantes
            Forced_leagues = ["ChL", "EuL", "ICC", "Ger", "Mar", "Eng", "Fra", "LE", "Cl"]


            if response.data:
                # Extraire les noms de ligues uniques
                all_leagues = list(set(item['LEAGUE'].strip() for item in response.data if item.get('LEAGUE')))
                
                # Séparer les favoris des autres ligues
                favorites = [league for league in favorite_leagues if league in all_leagues]
                others = sorted([league for league in all_leagues if league not in favorite_leagues])
                
                # Combiner favoris et autres ligues
                leagues = Forced_leagues + favorites + others
                leagues.insert(0, "All Leagues")  # Ajouter "All Leagues" au début

                # Mettre à jour les options du dropdown avec les ligues organisées
                self.filter_dropdown.options = [ft.dropdown.Option(league) for league in leagues]
                self.filter_dropdown.value = "All Leagues"  # Définir la valeur par défaut
                self.page.update()  # Rafraîchir la page pour afficher le dropdown mis à jour
            else:
                print("No league found.")
        except Exception as e:
            print(f"Error retrieving leagues: {e}")


    def get_filtered_data(self):
        # Construire la requête principale avec les filtres
        def query_func():
            query = self.supabase.table(TABLE_NAME).select("*", count='exact')

            if self.search_field.value:
                if len(self.search_field.value) >= self.min_search_length:
                    # Remove spaces and trim using strip()
                    search_value = self.search_field.value.strip()
                    # Vérifie l'état du bouton "Away"
                    if self.away_toggle.value:  # Si le switch est activé (Away)
                        query = query.ilike('TEAM2', f'{search_value}')
                    else:  # Si le switch est désactivé
                        query = query.ilike('TEAM1', f'{search_value}')
                elif len(self.search_field.value) > 0:
                    return []

            if self.filter_dropdown.value and self.filter_dropdown.value != "All Leagues":
                query = query.eq('LEAGUE', self.filter_dropdown.value)

            # Filtres ODD 1
            if self.odd1_field.value or self.odd_adjust_field.value:
                try:
                    odd1_value = float(self.odd1_field.value if self.odd1_field.value is not None else 0)
                    adjustment_value = float(self.odd_adjust_field.value if self.odd_adjust_field.value is not None else 0)
                    min_value = odd1_value - adjustment_value
                    max_value = odd1_value + adjustment_value
                    query = query.gte('ODD1', min_value).lte('ODD1', max_value)
                except ValueError:
                    pass

            # Filtres ODD X
            if self.oddx_field.value:
                try:
                    oddx_value = float(self.oddx_field.value) if self.oddx_field.value is not None else 0
                    adjustment_value = float(self.odd_adjust_field.value) if self.odd_adjust_field.value is not None else 0
                    min_value = oddx_value - adjustment_value
                    max_value = oddx_value + adjustment_value
                    query = query.gte('ODDX', min_value).lte('ODDX', max_value)
                except ValueError:
                    pass

            # Filtres ODD 2
            if self.odd2_field.value:
                try:
                    odd2_value = float(self.odd2_field.value) if self.odd2_field.value is not None else 0
                    adjustment_value = float(self.odd_adjust_field.value) if self.odd_adjust_field.value is not None else 0
                    min_value = odd2_value - adjustment_value
                    max_value = odd2_value + adjustment_value
                    query = query.gte('ODD2', min_value).lte('ODD2', max_value)
                except ValueError:
                    pass

            # Ajouter l'ordre décroissant par ID
            query = query.order('ID', desc=True)
            
            # Pagination
            start = self.current_page * self.page_size
            query = query.range(start, start + self.page_size - 1)

            return query.execute()
        try:
            # Exécuter la requête principale
            response = self.execute_with_retry(query_func)
            self.filtered_records = response.count

            # Construire une fonction pour réutiliser les filtres
            def apply_filters(base_query):
                if self.search_field.value:
                    if len(self.search_field.value) >= self.min_search_length:
                        # Remove spaces and trim using strip()
                        search_value = self.search_field.value.strip()
                        # Vérifie l'état du bouton "Away"
                        if self.away_toggle.value:  # Si le switch est activé (Away)
                            base_query = base_query.ilike('TEAM2', f'{search_value}')
                        else:  # Si le switch est désactivé
                            base_query = base_query.ilike('TEAM1', f'{search_value}')
                    else:  # Si la valeur du champ est trop courte
                        return base_query  # Return the original query instead of empty list
                if self.filter_dropdown.value and self.filter_dropdown.value != "All Leagues":
                    base_query = base_query.eq('LEAGUE', self.filter_dropdown.value)
                if self.odd1_field.value or self.odd_adjust_field.value:
                    try:
                        odd1_value = float(self.odd1_field.value if self.odd1_field.value is not None else 0)
                        adjustment_value = float(self.odd_adjust_field.value if self.odd_adjust_field.value is not None else 0)
                        min_value = odd1_value - adjustment_value
                        max_value = odd1_value + adjustment_value
                        base_query = base_query.gte('ODD1', min_value).lte('ODD1', max_value)
                    except ValueError:
                        pass
                if self.oddx_field.value:
                    try:
                        oddx_value = float(self.oddx_field.value) if self.oddx_field.value is not None else 0
                        adjustment_value = float(self.odd_adjust_field.value) if self.odd_adjust_field.value is not None else 0
                        min_value = oddx_value - adjustment_value
                        max_value = oddx_value + adjustment_value
                        base_query = base_query.gte('ODDX', min_value).lte('ODDX', max_value)
                    except ValueError:
                        pass
                if self.odd2_field.value:
                    try:
                        odd2_value = float(self.odd2_field.value) if self.odd2_field.value is not None else 0
                        adjustment_value = float(self.odd_adjust_field.value) if self.odd_adjust_field.value is not None else 0
                        min_value = odd2_value - adjustment_value
                        max_value = odd2_value + adjustment_value
                        base_query = base_query.gte('ODD2', min_value).lte('ODD2', max_value)
                    except ValueError:
                        pass
                return base_query

            # Comptage des résultats "1", "X", "2"
            def count_result_1():
                return apply_filters(
                    self.supabase.table(TABLE_NAME).select("*", count='exact').eq('RESULT', '1')
                ).execute()

            def count_result_X():
                return apply_filters(
                    self.supabase.table(TABLE_NAME).select("*", count='exact').eq('RESULT', 'X')
                ).execute()

            def count_result_2():
                return apply_filters(
                    self.supabase.table(TABLE_NAME).select("*", count='exact').eq('RESULT', '2')
                ).execute()

            def count_over():
                return apply_filters(
                    self.supabase.table(TABLE_NAME).select("*", count='exact')
                    .gt('GOAL1 + GOAL2', 2)
                ).execute()

            def count_bts():
                return apply_filters(
                    self.supabase.table(TABLE_NAME).select("*", count='exact')
                    .gt('GOAL1', 0)
                    .gt('GOAL2', 0)
                ).execute()

            # Execute all counts with retry mechanism
            result_1 = self.execute_with_retry(count_result_1)
            result_X = self.execute_with_retry(count_result_X)
            result_2 = self.execute_with_retry(count_result_2)
            result_over = self.execute_with_retry(count_over)
            result_bts = self.execute_with_retry(count_bts)

            self.filtered_records_1 = result_1.count
            self.filtered_records_X = result_X.count
            self.filtered_records_2 = result_2.count
            self.filtered_over = result_over.count
            self.filtered_bts = result_bts.count

            # Retourner les données filtrées
            return response.data

        except Exception as e:
            print(f"Erreur lors de la récupération des données: {e}")
            return []

    def calculate_percentage(self, part, total):
        return (part / total * 100) if total > 0 else 0

    def update_stats_card(self):
        total = f"{self.total_records:,}".replace(',', ' ')
        filtered = f"Games: {self.filtered_records:,}".replace(',', ' ')
        filtered_1 = f"{self.filtered_records_1:,}".replace(',', ' ')
        filtered_X = f"{self.filtered_records_X:,}".replace(',', ' ')
        filtered_2 = f"{self.filtered_records_2:,}".replace(',', ' ')
        filtered_over = f"{self.filtered_over:,}".replace(',', ' ')
        filtered_bts = f"{self.filtered_bts:,}".replace(',', ' ')

        # Définir les autres en-têtes du tableau
        headers = [ft.Text(filtered, size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                  ft.Text("R:1", size=16, text_align=ft.TextAlign.CENTER), 
                  ft.Text("R:X", size=16, text_align=ft.TextAlign.CENTER), 
                  ft.Text("R:2", size=16, text_align=ft.TextAlign.CENTER), 
                  ft.Text("O/U", size=16, text_align=ft.TextAlign.CENTER), 
                  ft.Text("BTS", size=16, text_align=ft.TextAlign.CENTER)]

        # Données du tableau avec des cellules initialisées à zéro par défaut
        def safe_float(value):
            try:
                return float(value)
            except ValueError:
                return 0.0

        rows = [
            ["ODDS 1X2", 
            f"{filtered_1} ({self.calculate_percentage(safe_float(self.filtered_records_1), safe_float(self.filtered_records)):.1f}%) ({self.calculate_percentage(safe_float(self.filtered_records_1) * safe_float(self.odd1_field.value), (safe_float(self.filtered_records) * safe_float(self.odd1_field.value) * safe_float(self.oddx_field.value)* safe_float(self.odd2_field.value))/10):.1f}%)",
            f"{filtered_X} ({self.calculate_percentage(safe_float(self.filtered_records_X), safe_float(self.filtered_records)):.1f}%) ({self.calculate_percentage(safe_float(self.filtered_records_X) * safe_float(self.oddx_field.value), (safe_float(self.filtered_records) * safe_float(self.odd1_field.value) * safe_float(self.oddx_field.value)* safe_float(self.odd2_field.value))/10):.1f}%)", 
            f"{filtered_2} ({self.calculate_percentage(safe_float(self.filtered_records_2), safe_float(self.filtered_records)):.1f}%) ({self.calculate_percentage(safe_float(self.filtered_records_2) * safe_float(self.odd2_field.value), (safe_float(self.filtered_records) * safe_float(self.odd1_field.value) * safe_float(self.oddx_field.value)* safe_float(self.odd2_field.value))/10):.1f}%)", 
            f"{filtered_over} ({self.calculate_percentage(safe_float(self.filtered_over), safe_float(self.filtered_records)):.1f}%)", 
            f"{filtered_bts} ({self.calculate_percentage(safe_float(self.filtered_bts), safe_float(self.filtered_records)):.1f}%)"],
            ["ODD 1", 0, 0, 0, 0, 0],
            ["ODD X", 0, 0, 0, 0, 0],
            ["ODD 2", 0, 0, 0, 0, 0],
        ]

        # Contenu du tableau
        table_content = ft.Column(
            [
                # En-têtes de colonnes
                ft.Row(
                    [
                        ft.Container(
                            content=header,
                            expand=1,
                            alignment=ft.alignment.center
                        ) for header in headers
                    ],
                    spacing=0,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(thickness=2),
            ] +
            [
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    ft.Text(str(cell), size=14, text_align=ft.TextAlign.CENTER),
                                    expand=1,
                                    alignment=ft.alignment.center
                                )
                                for cell in row
                            ],
                            spacing=0,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        ft.Divider(height=1, thickness=1, color=ft.colors.BLACK12)
                    ],
                    spacing=0
                )
                for row in rows
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )

        # Ajouter un conteneur avec le tableau défilable
        scrollable_table = ft.ListView(
            controls=[table_content],
            spacing=10,
            padding=ft.padding.symmetric(horizontal=20),
            auto_scroll=False,
            expand=True
        )

        # Carte contenant le tableau
        self.stats_card.content = ft.Container(
            content=ft.Column(
                [
                    scrollable_table
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=5
            ),
            padding=ft.padding.all(5),
            border_radius=4,
            expand=True
        )

        # Mise à jour de la page
        self.page.update()



    def refresh_data(self, e=None):
        data = self.get_filtered_data()
        
        # Création des lignes du tableau avec la colonne RESULT ajoutée
        self.data_table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(f"{item.get('DATE', '')}\n{item.get('H', '')}")),
                    ft.DataCell(ft.Text(item.get('LEAGUE', ''))),
                    ft.DataCell(ft.Text(f"{item.get('TEAM1', '')}\n{item.get('TEAM2', '')}")),
                    ft.DataCell(ft.Text(str(item.get('ODD1', '')))),
                    ft.DataCell(ft.Text(str(item.get('ODDX', '')))),
                    ft.DataCell(ft.Text(str(item.get('ODD2', '')))),
                    ft.DataCell(ft.Text(str(item.get('RESULT', '')))),
                    ft.DataCell(ft.Text(f"{item.get('GOAL1', '')} - {item.get('GOAL2', '')}")),
                ]
            ) for item in data
        ]
        
        # Mise à jour des statistiques
        self.update_stats_card()
        
        # Mise à jour de la pagination
        current_range_start = self.current_page * self.page_size + 1
        current_range_end = min((self.current_page + 1) * self.page_size, self.filtered_records)
        
        self.pagination_row.controls = [
            ft.IconButton(
                icon=ft.icons.FIRST_PAGE,
                on_click=self.first_page,
                disabled=self.current_page == 0
            ),
            ft.IconButton(
                icon=ft.icons.NAVIGATE_BEFORE,
                on_click=self.prev_page,
                disabled=self.current_page == 0
            ),
            ft.Text(
                f"{current_range_start}-{current_range_end} sur {self.filtered_records}",
                size=16,
                weight=ft.FontWeight.BOLD
            ),
            ft.IconButton(
                icon=ft.icons.NAVIGATE_NEXT,
                on_click=self.next_page,
                disabled=(self.current_page + 1) * self.page_size >= self.filtered_records
            ),
            ft.IconButton(
                icon=ft.icons.LAST_PAGE,
                on_click=self.last_page,
                disabled=(self.current_page + 1) * self.page_size >= self.filtered_records
            ),
        ]
        
        self.page.update()

    def first_page(self, e):
        self.current_page = 0
        self.refresh_data()

    def last_page(self, e):
        self.current_page = (self.filtered_records - 1) // self.page_size
        self.refresh_data()

    def next_page(self, e):
        self.current_page += 1
        self.refresh_data()

    def prev_page(self, e):
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_data()

    def search_data(self, e):
        self.current_page = 0
        self.refresh_data()

    def main(self, page: ft.Page):
        self.page = page
        page.title = "BETSMARTER"
        page.window.width = 1200
        page.window.height = 800
        page.padding = 5
        page.theme_mode = ft.ThemeMode.LIGHT

#####################################  MAIN FUNCTION   #####################################

        # Fonction pour basculer entre le mode clair et sombre
        def toggle_theme(e):

            if page.theme_mode == ft.ThemeMode.LIGHT:
                page.theme_mode = ft.ThemeMode.DARK
                e.control.icon = ft.icons.WB_SUNNY
            else:
                page.theme_mode = ft.ThemeMode.LIGHT
                e.control.icon = ft.icons.NIGHTLIGHT_ROUND
            page.update()

        # Fonction qui gère le clic sur un item du menu popup
        def check_item_clicked(e):
            e.control.checked = not e.control.checked
            page.update()

        # Fonction pour changer de page
        def change_page(index):
             # pageMatches.visible = (index == 0)
             # pageAnalytics.visible = (index == 1)
             # pagePrediction.visible = (index == 2)
            page.update()
#####################################  AppBar  #####################################

        page.appbar = ft.AppBar(
            leading=ft.Image(
                src="https://gffawshxojiqpkdqxerb.supabase.co/storage/v1/object/sign/IMG/LOGO_BETSMARTER.png?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1cmwiOiJJTUcvTE9HT19CRVRTTUFSVEVSLnBuZyIsImlhdCI6MTczMjM3MjQxNCwiZXhwIjoyMDQ3NzMyNDE0fQ.Hl6pTbUfTiV9WTh9enVqtqP9aPj75DMPNPNTRZ-AnO4",
                width=60,
                height=60,
                fit=ft.ImageFit.CONTAIN,
            ),
            leading_width=60,
            title=ft.Text(
                "BET SMARTER",
                text_align=ft.TextAlign.CENTER,
                font_family="Montserrat",  # Changer la police à Montserrat
                size=20,  # Taille du titre ajustée
                weight=ft.FontWeight.BOLD,  # En gras pour renforcer l'impact
                color="#0b0c24",  # Couleur personnalisée en hexadécimal (ici vert)
            ),
            center_title=True,  # Pour centrer le titre dans l'AppBar
            bgcolor=ft.colors.SURFACE_VARIANT,
            actions=[
                ft.IconButton(ft.icons.NIGHTLIGHT_ROUND, on_click=toggle_theme),
                ft.IconButton(ft.icons.NOTIFICATIONS),
                ft.PopupMenuButton(
                    items=[
                        ft.PopupMenuItem(text="Item 1"),
                        ft.PopupMenuItem(),  # divider
                        ft.PopupMenuItem(
                            text="Checked item", checked=False, on_click=check_item_clicked
                        ),
                    ]
                ),
            ],
        )
#####################################  AppBar END  #####################################

#####################################  NavigationBar  #####################################

        # NavigationBar
        page.navigation_bar = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon=ft.icons.HOME, label="Matches"),
                ft.NavigationBarDestination(icon=ft.icons.ANALYTICS, label="Analytics"),
                ft.NavigationBarDestination(icon=ft.icons.BATCH_PREDICTION,selected_icon=ft.icons.BATCH_PREDICTION_OUTLINED,label="Prediction")
            ],
            on_change=lambda e: change_page(e.control.selected_index)
        )
#####################################  NavigationBar END  #####################################

###################### Récupération du nombre total d'enregistrements ###########################
        self.total_records = self.get_total_count()
        
        # Carte des statistiques
        self.stats_card = ft.Card(
            elevation=1,
            margin=5
        )
        
        # Champs de recherche et filtres
        self.search_field = ft.TextField(
            label="Find a team",
            hint_text=f"Min {self.min_search_length} characters",  # Texte affiché à l'intérieur du champ vide
            width=200,
            on_change=self.search_data,
            # helper_text=f"Minimum {self.min_search_length} characters",
            prefix_icon=ft.icons.SEARCH
        )
        
        # Switch (On/Off pour "Away")
        self.away_toggle = ft.Switch(
            label="Away",  # Texte affiché à côté du switch
            value=False,  # État initial du switch (désactivé par défaut)
            on_change=self.search_data,  # Fonction appelée lors du changement d'état
        )
        
        # Ajoutez ceci dans votre classe DataViewerApp
        self.odd_adjust_field = ft.TextField(
            value="0.00",  # Valeur initiale
            width=60,
            text_align=ft.TextAlign.RIGHT,
            # label="Edge OF Odds",
            # helper_text=f"Edge OF Odds\nMin 0.00 Max 0.50",
            read_only=True  # Rendre le champ en lecture seule
        )

        self.filter_dropdown = ft.Dropdown(
            label="By League",
            width=200,
            options=[ft.dropdown.Option("All Leagues")],
            value="All Leagues",
            # helper_text=f"Choose League",
            on_change=self.search_data
        )
        
        # Chargement des ligues
        self.load_leagues()
        
        # Champs ODD
        self.odd1_field = ft.TextField(
            label="ODD1",
            width=100,
            on_change=self.search_data,
            keyboard_type=ft.KeyboardType.NUMBER
        )

        # Champ de texte pour afficher la valeur
        self.edge_of_odds_field = ft.TextField(
            label="Edge OF Odds",
            value="0.00",  # Valeur initiale
            width=100,
            text_align=ft.TextAlign.RIGHT,
            read_only=True  # Rendre le champ en lecture seule
    )
        self.oddx_field = ft.TextField(
            label="ODDX",
            width=100,
            on_change=self.search_data,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        self.odd2_field = ft.TextField(
            label="ODD2",
            width=100,
            on_change=self.search_data,
            keyboard_type=ft.KeyboardType.NUMBER
        )

        # Tableau de données
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Time")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("League")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("Teams")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("1")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("X")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("2")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("R")),  # Colonne vide pour aligner avec l'en-tête
                ft.DataColumn(ft.Text("S")),  # Colonne vide pour aligner avec l'en-tête
            ],
            rows=[],  # Vous remplirez les lignes plus tard
        )

        # Conteneur scrollable pour le DataTable
        data_container = ft.Container(
            content=ft.Column(
                [self.data_table],
                scroll=ft.ScrollMode.AUTO,  # Active le défilement vertical
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,  # Aligne horizontalement
            ),
            # bgcolor=ft.colors.WHITE,
            border=ft.border.all(1, ft.colors.BLACK12),
            border_radius=8,
            height=500,  # Hauteur fixe pour le scroll
            expand=True,  # Permet au conteneur d'occuper toute la largeur
        )

        
        # Ligne de pagination
        self.pagination_row = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=20
        )
        
        # Création de la carte des filtres
        filters_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        # Groupe 1 - Filtres ODD
                        ft.Container(
                            content=ft.Row(
                                [
                                    self.odd1_field,
                                    self.oddx_field,
                                    self.odd2_field,
                                    ft.Text("", width=30, text_align=ft.TextAlign.RIGHT),
                                    ft.ElevatedButton("-", on_click=lambda e: self.update_value(self.odd_adjust_field, -0.05)),
                                    self.odd_adjust_field,
                                    ft.ElevatedButton("+", on_click=lambda e: self.update_value(self.odd_adjust_field, 0.05)),
                                ],
                                alignment=ft.MainAxisAlignment.START,
                                spacing=10
                            ),
                            padding=10,
                        ),
                        ft.Divider(height=1, color=ft.colors.BLACK26),
                        # Groupe 2 - Recherche et filtres de ligue
                        ft.Container(
                            content=ft.Row(
                                [
                                    self.search_field,
                                    self.away_toggle,
                                    self.filter_dropdown,
                                ],
                                alignment=ft.MainAxisAlignment.START,
                                spacing=10
                            ),
                            padding=10,
                        ),
                    ],
                    spacing=0,
                ),
                padding=0,
            ),
        )

        # Structure de la page
        main_container = ft.Container(
            content=ft.Column(
                [
                    filters_card,
                    self.stats_card,
                    data_container,
                    self.pagination_row
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=10,
                expand=True,
            ),
            expand=True,
            padding=10,
        )

        page.add(main_container)
        
        # Chargement initial
        self.refresh_data()

if __name__ == '__main__':
    app = DataViewerApp()
    ft.app(target=app.main)