# Política de documentación

[English](DOCUMENTATION_POLICY.md) | [Español](DOCUMENTATION_POLICY-es.md)

La documentación del proyecto usa el inglés como idioma principal. Cada documento Markdown propio tiene una variante completa en español al lado: `NAME.md` y `NAME-es.md`. Ambas variantes describen el mismo comportamiento, evidencia y limitaciones.

Actualizá ambos archivos en el mismo cambio. Traducí títulos, párrafos, listas, descripciones de tablas y etiquetas de enlaces. Enlazá a la variante del mismo idioma cuando el destino tenga ambas versiones y mantené un selector de idioma cerca del comienzo de cada documento.

Conservá sin cambios los comandos, ejemplos de código, rutas, nombres de archivo, identificadores, nombres de API, hashes y salidas registradas. Los nombres de archivo existentes permanecen estables aunque contengan palabras en español, porque los scripts y las referencias históricas pueden depender de ellos.

Los logs históricos, informes JSON, manifiestos, evidencia archivada, documentación de terceros y textos oficiales de licencias conservan su contenido original. Traducí la explicación propia que los acompaña en lugar de reescribir la evidencia. La traducción de documentación no cambia el estado de validación de una build.

La conversión bilingüe inicial usa modelos de traducción locales con comprobaciones estructurales. El significado técnico sigue requiriendo revisión editorial al modificar un documento; las comprobaciones automáticas no pueden establecer la exactitud de la traducción.

Comprobá los pares y sus enlaces de navegación desde la raíz del repositorio:

```sh
python3 tools/check-docs-bilingual.py
```
