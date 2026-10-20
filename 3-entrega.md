Tercera Entrega: Despliegue de Recursos de Infraestructura (IaC)



Objetivo Principal:

Implementar la arquitectura diseñada utilizando Infraestructura como Código (IaC) con Terraform, incorporando las mejores prácticas y los conceptos avanzados vistos en clase.



Entregables:



1. Repositorio de Código 

  - Archivos Terraform completos

  - Implementación de correcciones previas

  - Cumplimiento de requisitos específicos



2. Diagrama de Arquitectura Actualizado

  - Reflejo de cambios implementados

  - Alineación con el código Terraform



3. Documentación Detallada (README)

  - Descripción de módulos

  - Explicación de funciones y meta-argumentos

  - Guía paso a paso para ejecución

 - Inclusión de pipeline de GitHub Actions para ejecución de Terraform, en el que se deberá poder deployar la arquitectura (init, validate, plan, apply)



Requisitos Técnicos:



1. Módulos Terraform

  - Mínimo un módulo personalizado

  - Mínimo un módulo externo



2. Variables y Outputs

  - Uso efectivo para parametrización



3. Funciones Terraform

  - Implementación de al menos 4 funciones



4. Meta-argumentos

  - Uso de mínimo 3 entre:

   - depends_on

   - for_each

   - count

   - lifecycle



5. Estructura del Proyecto

  - Organización lógica de archivos

  - Nomenclatura consistente

  - Aplicación del principio DRY



Proceso de Entrega:

- Pull request al repositorio proporcionado

- Inclusión del hash del commit en la entrega del campus

- El pipeline debe ejecutarse correctamente en el pull request



Consideraciones Importantes:

- Se permite el uso de datos simulados (mock data)

- No se requiere demostración en vivo

- La capacidad de la cátedra de ejecutar el código es crítica para la aprobación



Criterios de Evaluación:

1. Implementación correcta de componentes requeridos

2. Complejidad y sofisticación de las soluciones

3. Calidad del diseño y estructura del código

4. Claridad en la documentación y guías de ejecución

5. Correcta implementación del pipeline CI/CD



Recursos Recomendados:

- Terraform Best Practices for AWS users (https://github.com/ozbillwang/terraform-best-practices)

- Terraform Best Practices (https://www.terraform-best-practices.com/)

- Documentación oficial de Terraform para AWS (https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

Tutorial para uso de Git / GitHub