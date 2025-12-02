import random
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from biblioteca.models import Categoria, Autor, Libro, Material

# --- Listas de Datos para Generación Aleatoria ---
PREFIJOS_LIBRO = ["Fundamentos de", "Principios de", "Introducción a", "Técnicas Avanzadas de", "El Manual de", "Guía Práctica de"]
TEMAS_LIBRO = ["Aerodinámica Aplicada", "Estructuras de Aeronaves", "Aviónica Moderna", "Control de Vuelo", "Mantenimiento Aeronáutico", "Propulsión a Chorro", "Navegación Aérea"]
AUTORES_DATA = [
    ("John", "Anderson"), ("Michael", "Smith"), ("David", "Johnson"), ("Chris", "Lee"),
    ("Robert", "Brown"), ("William", "Davis"), ("James", "Wilson"), ("Richard", "Moore"),
    ("Charles", "Taylor"), ("Thomas", "Clark"), ("Maria", "Garcia"), ("Laura", "Lopez"),
    ("Ana", "Martinez"), ("Sophie", "Dubois"), ("Hans", "Schmidt")
]
TIPOS_MATERIAL = ["Manual de Mantenimiento", "Manual de Vuelo", "Guía de Reparación", "Diagrama de Sistemas", "Boletín Técnico"]
MODELOS_AVION = ["Boeing 737", "Airbus A320", "Cessna 172", "Boeing 787", "Embraer E190", "Airbus A350", "Gulfstream G650", "Bombardier CRJ"]
ENTIDADES = ["DGAC", "Boeing", "Airbus", "EASA", "FAA", "Pratt & Whitney", "Rolls-Royce"]


class Command(BaseCommand):
    help = 'Realiza una carga masiva de 100 libros y 100 materiales de aviación.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- INICIANDO CARGA MASIVA (v3 - Comando) ---"))

        # --- 1. LIMPIEZA PREVIA ---
        self.stdout.write("Paso 1: Limpiando datos de prueba antiguos...")
        libros_borrados, _ = Libro.objects.filter(isbn__startswith="97800010").delete()
        materiales_borrados, _ = Material.objects.filter(codigo__startswith="DGAC-DOC-").delete()
        self.stdout.write(f"-> {libros_borrados} libros y {materiales_borrados} materiales de prueba eliminados.")

        # --- 2. CREAR CATEGORÍAS ---
        self.stdout.write("Paso 2: Creando 5 Categorías...")
        cat_aero, _ = Categoria.objects.get_or_create(nombre="Aerodinámica")
        cat_mec, _ = Categoria.objects.get_or_create(nombre="Mecánica de Aviación")
        cat_nav, _ = Categoria.objects.get_or_create(nombre="Navegación Aérea")
        cat_prop, _ = Categoria.objects.get_or_create(nombre="Sistemas de Propulsión")
        cat_man, _ = Categoria.objects.get_or_create(nombre="Manuales de Vuelo")
        categorias = [cat_aero, cat_mec, cat_nav, cat_prop, cat_man]
        self.stdout.write(f"-> {len(categorias)} Categorías listas.")

        # --- 3. CREAR AUTORES ---
        self.stdout.write("Paso 3: Creando 15 Autores...")
        autores = []
        for nombre, apellido in AUTORES_DATA:
            autor, _ = Autor.objects.get_or_create(nombre=nombre, apellido=apellido)
            autores.append(autor)
        self.stdout.write(f"-> {len(autores)} Autores listos.")

        # --- 4. CREAR 100 LIBROS ---
        self.stdout.write("Paso 4: Creando 100 Libros...")
        libros_creados_count = 0
        for i in range(100):
            cat = categorias[i % 5]
            aut = random.choice(autores)
            titulo = f"{random.choice(PREFIJOS_LIBRO)} {random.choice(TEMAS_LIBRO)} (Ed. {i+1})"
            isbn_unico = f"97800010{i:05d}"
            
            try:
                obj, created = Libro.objects.get_or_create(
                    isbn=isbn_unico,
                    defaults={
                        'titulo': titulo, 'autor': aut, 'categoria': cat,
                        'sinopsis': "Aqui va la sinopsis",
                        'cantidad': random.randint(1, 5)
                    }
                )
                if created:
                    libros_creados_count += 1
            except IntegrityError:
                self.stderr.write(f"Error: No se pudo crear libro con ISBN {isbn_unico}")
                
        self.stdout.write(self.style.SUCCESS(f"-> {libros_creados_count} Libros nuevos creados."))

        # --- 5. CREAR 100 MATERIALES ---
        self.stdout.write("Paso 5: Creando 100 Materiales (Manuales)...")
        materiales_creados_count = 0
        for i in range(100):
            titulo = f"{random.choice(TIPOS_MATERIAL)}: {random.choice(MODELOS_AVION)} (Rev. {i+1})"
            codigo_unico = f"DGAC-DOC-{i:05d}"
            
            try:
                obj, created = Material.objects.get_or_create(
                    codigo=codigo_unico,
                    defaults={
                        'titulo': titulo, 'autor': random.choice(ENTIDADES),
                        'tipo': "Manual Técnico", 'formato': "Físico / Digital",
                        'ubicacion': f"Archivo {random.randint(1, 5)}-{chr(65 + (i % 5))}",
                        'cantidad': random.randint(1, 3)
                    }
                )
                if created:
                    materiales_creados_count += 1
            except IntegrityError:
                self.stderr.write(f"Error: No se pudo crear material con Código {codigo_unico}")

        self.stdout.write(self.style.SUCCESS(f"-> {materiales_creados_count} Materiales nuevos creados."))
        self.stdout.write(self.style.SUCCESS("\n--- CARGA MASIVA FINALIZADA ---"))