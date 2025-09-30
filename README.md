# Módulos Odoo desarrollados

Este repositorio contiene una colección de módulos desarrollados para Odoo (orientado a Odoo 18+/17+).  
El código mostrado incluye los manifiestos y la estructura mínima necesaria; por motivos legales no todo el código está publicado.

A continuación hay un resumen por módulo indicando: funcionalidad principal, dependencias clave y el impacto/compatibilidad con el ecosistema Odoo.

Notas de lectura:
- "Dependencias" indica módulos de Odoo requeridos que condicionan la compatibilidad.
- "Impacto" describe cómo el módulo se integra o modifica comportamientos estándar de Odoo.

Lista de módulos
-----------------

1) asset_loan_extension
   - Funcionalidad: Añade campos para registrar préstamos sobre activos fijos (historial, fechas y vínculo contable).
   - Dependencias clave: `base`, `account_asset`.
   - Impacto en Odoo: Extiende el modelo de activos; integra flujos de préstamo con la contabilidad de activos, sin romper APIs públicas.

2) asset_responsible_tracking
   - Funcionalidad: Gestión de responsables de activos fijos, con vistas y reglas de acceso.
   - Dependencias clave: `account_asset`, `hr`.
   - Impacto: Añade responsabilidad organizacional a activos; útil para auditoría y trazabilidad.

3) barcode_operations_extension
   - Funcionalidad: Muestra campos adicionales (origen y orden de compra) en la interfaz de operaciones por código de barras.
   - Dependencias clave: `stock`, `stock_barcode`, `barcodes`, `stock_picking_extra_fields`.
   - Impacto: Mejora la usabilidad en pantallas de escaneo sin alterar la lógica de inventario; agrega assets frontend.

4) bloqueo_factura_ventas_borrador
   - Funcionalidad: Control/gestión de facturas en estado borrador mediante seguridad y vistas.
   - Dependencias clave: `account`, `sale`.
   - Impacto: Cambia flujos de validación de facturas para prevenir edición no deseada; afecta permisos y accesos.

5) comisiones_gadint
	 - Funcionalidad (detallada): Sistema completo para manejar comisiones de vendedores externos con:
		 - Identificación de vendedores externos en contactos (campo booleano).
		 - Gestión de equipos/tipos (Líder / Vendedor) y planes de comisión.
		 - Campos en cotizaciones y facturas para asignar vendedores externos.
		 - Automatización de la liquidación de comisiones basada en pagos de facturas.
		 - Sincronización entre pedidos de venta y facturas para mantener consistencia en la asignación de comisiones.
		 - Seguimiento con chatter (mensajería) para actividades y seguimiento de comisiones.
	 - Dependencias clave: `base`, `mail`, `sale`, `account`, `sale_commission`.
	 - Impacto: Proporciona una capa empresarial sobre el sistema de comisiones nativo de Odoo 18; ideal cuando se necesita gestión de vendedores externos y lógica de pagos automáticos. Revisar para evitar solapamientos si se activa el módulo nativo de comisiones.

6) crm_social_extension
	 - Funcionalidad (detallada): Extiende CRM con funcionalidades sociales y de marketing:
		 - Campos para URLs de redes sociales (Facebook, LinkedIn, Twitter) en contactos.
		 - Pestaña social en el perfil del cliente con iconos y enlaces.
		 - Indicador visual de completitud de perfil social y filtros por estado de completitud.
		 - Página pública (website) para promocionar clientes con datos sociales.
		 - Búsqueda avanzada por nombre y cuentas sociales.
		 - Lead scoring automático (0-100) basado en completitud y engagement social.
		 - Automatizaciones de marketing que generan actividades de seguimiento para perfiles incompletos.
		 - Tareas automáticas para el equipo de ventas según el engagement.
		 - Soporte multi-sitio, pruebas unitarias (Python + QUnit), optimizaciones de consultas y assets frontend para widget social.
	 - Dependencias clave: `base`, `crm`, `website`, `mail`, `portal`, `marketing_automation`, `sales_team`, `board`.
	 - Impacto: Enriquecerá la gestión de leads y clientes con información social, mejorando las campañas de marketing y la priorización de leads; añade assets y vistas que deben integrarse con el tema del sitio web.

7) commission_reports
	 - Funcionalidad (detallada): Wizard y reporte para cálculo de comisiones con:
		 - Filtros avanzados (fechas, vendedores, clientes, categorías, sucursales y almacenes).
		 - Cálculo automático de costos, beneficios y márgenes por línea.
		 - Agrupaciones flexibles (por vendedor, cliente, categoría, producto, sucursal, almacén).
		 - Exportación a PDF y Excel en formatos optimizados para impresión (A4 horizontal) y con totales/subtotales.
		 - Campos detallados: cliente, factura, producto, cantidad, costo unitario, costo total, precio, beneficio y % margen.
	 - Dependencias clave: `base`, `account`, `product`, `stock`, `sale`, `report_xlsx`.
	 - Impacto: Ofrece reportes listos para contabilidad y pagos de comisiones; recomendable usarlo junto a módulos de comisiones para automatizar flujos de pago.

8) custom_landed_cost_manufacturing
   - Funcionalidad: Añade campo y visibilidad para costos en destino en productos y fabricación.
   - Dependencias clave: `product`, `stock_landed_costs`.
   - Impacto: Complementa el cálculo de landed costs y lo hace visible en pantallas de producto/producción.

9) hr_payroll_provision_management
   - Funcionalidad: Gestión de provisiones de nómina (XIII/XIV) y secuencias, vistas y reglas.
   - Dependencias clave: `hr_contract`, `hr_work_entry_contract`, `hr_xiii`.
   - Impacto: Añade integración con nómina para provisiones y reglas contables asociadas.

10) hr_xiii
	- Funcionalidad: Cálculo y gestión del pago XIII.
	- Dependencias clave: `hr_payroll`, `hr_payslip_historic_income`.
	- Impacto: Extiende nómina con reglas y datos iniciales para XIII.

11) hr_xiv
	- Funcionalidad: Cálculo y gestión del pago XIV con seguimiento por SBU y provisiones automáticas.
	- Dependencias clave: `hr_payroll`, `hr_job_regime_base`.
	- Impacto: Similar a `hr_xiii`, agrega reglas y vistas para XIV.

12) importation_xlsx_report
		- Funcionalidad (detallada): Añade un botón en formularios de importación (solo cuando el estado es `done`) que genera un resumen XLSX con:
			- Logo y nombre de la compañía, identificador de la importación y fecha de liquidación.
			- Texto de moneda clarificador ("VALORES EN ...").
			- Tabla de ítems de liquidación (solo líneas con `is_landed_cost=True`).
			- Tabla de proveedores (únicos) implicados en la importación.
			- Tabla de productos con detalles tomados de `trade.costo_details`.
			- Tabla de descripciones fiscales (ITBIS y Gravamen).
		- Dependencias clave: `importation_reports`, `base`.
		- Impacto: Facilita la generación de documentación legal/contable para importaciones y acelera auditorías; requiere `xlsxwriter` para la generación de XLSX.

13) mo_bom_overview
	- Funcionalidad: Añade botón 'BOM Overview' en órdenes de fabricación en cualquier estado, con visualización tipo BOM Overview incluyendo landed costs.
	- Dependencias clave: `mrp`.
	- Impacto: Mejora la UX para responsables de producción; añade assets JS/CSS.

14) mrp_indirect_costs
		- Funcionalidad (detallada): Módulo que gestiona costos indirectos en fabricación con:
			- Creación automática de costos en destino al confirmar órdenes de fabricación.
			- Pestaña propia en la orden de fabricación para ver y editar líneas de costos indirectos a través de un modelo proxy.
			- Gestión manual y validación de líneas de costos antes del cierre de producción.
			- Sincronización bidireccional entre las líneas proxy en la orden y los `stock.landed.costs` relacionados.
			- Wizard de confirmación de cierre de producción que obliga a revisar costos indirectos.
		- Dependencias clave: `base`, `mrp`, `stock_landed_costs`, `mrp_landed_costs`, `custom_landed_cost_manufacturing`.
		- Impacto: Introduce controles y trazabilidad para absorber costos indirectos en la fabricación; debe integrarse con procesos de landed costs y contabilidad. Recomendado probar sobre instancias de staging antes de producción.

15) mrp_landed_costs_safe
	- Funcionalidad: Muestra y suma costos indirectos (landed costs) en análisis de órdenes de fabricación.
	- Dependencias clave: `mrp_landed_costs`.
	- Impacto: Mejora reportes de coste en fabricación.

16) product_loans
		- Funcionalidad (detallada): Sistema empresarial para gestionar préstamos de productos:
			- Tipos de almacén especializados y ubicaciones dinámicas para préstamos.
			- Gestión por producto y número de serie/lote, con estados de préstamo y trazabilidad completa.
			- Períodos de prueba y conversión automática a ventas cuando corresponde.
			- Wizards de resolución para manejar compras, devoluciones y préstamos continuos.
			- Contabilidad integrada: asientos de compromiso, cuentas de riesgo y ajustes automáticos.
			- Alertas automáticas para préstamos vencidos y actividades/notificaciones por email.
			- Dashboard analítico con métricas en tiempo real y reportes optimizados (SQL).
			- Validaciones avanzadas de stock que consideran reservas y concurrencia y límites configurables por cliente.
		- Dependencias clave: `base`, `stock`, `sale`, `account`, `mail`.
		- Impacto: Es una aplicación completa que cambia flujos de inventario y contabilidad; antes de instalar, revisar configuración de cuentas y almacenes.

17) purchase_warranty
	- Funcionalidad: Agrega flujo de "compra por garantía" en pedidos de compra y factura de proveedor heredada.
	- Dependencias clave: `purchase`, `account`, `stock`, `stock_reception_type`.
	- Impacto: Introduce nuevo comportamiento en recepciones y facturación; útil cuando la empresa maneja garantías específicas.

18) report_xlsx
	- Funcionalidad: Base común para generar reportes XLSX (módulo proveniente de OCA/ACSONE).
	- Dependencias clave: `base`, `web`; requiere `xlsxwriter`/`xlrd`.
	- Impacto: Biblioteca de reporting ampliamente usada; afecta a cualquier módulo que exporte XLSX.

19) sales_auditoria_report
	- Funcionalidad: Wizard para generar reportes de ventas orientados a auditoría, con export a PDF/XLSX y filtros específicos.
	- Dependencias clave: `account`, `account_reports`, `web`.
	- Impacto: Añade un flujo de auditoría específico que excluye borradores y agrupa por tipos de comprobante.

20) serial_number_validation / stock_serial_validation
		- Funcionalidad (detallada): Validaciones en tiempo real y herramientas para gestión de números de serie:
			- Prevención de duplicados dentro del mismo picking y validaciones cruzadas contra entregas pendientes.
			- Verificación de disponibilidad en stock antes de permitir su uso en una operación.
			- Integración con la interfaz de códigos de barras (assets JS) para validación durante el escaneo.
			- Mensajes de error y manejo robusto de excepciones (localizados en español en la versión del repo).
			- Datos de configuración y fixtures bajo `data/serial_validation_data.xml`.
		- Dependencias clave: `base`, `stock`, `barcodes`, `stock_barcode`.
		- Impacto: Aumenta la confiabilidad del inventario en procesos de picking y entrega; debe coordinarse si existen otros módulos que afecten el mismo flujo de seriales.

21) stock_lot_filter_available
	- Funcionalidad: Muestra solo números de serie/lotes con stock disponible en entregas y transferencias.
	- Dependencias clave: `stock`, `product`.
	- Impacto: Mejora la selección de lotes/series en operaciones de picking.

22) stock_picking_conduce_report
	- Funcionalidad: Añade reporte 'Conduce' para picking con layout personalizado y agrupación de productos con trazabilidad.
	- Dependencias clave: `stock`, `stock_picking_responsable`, `stock_picking_extra_fields`.
	- Impacto: Añade opciones de impresión específicas para logística.

23) stock_picking_extra_fields
	- Funcionalidad: Extiende `stock.picking` con campos de Condición, Vía y Orden de compra.
	- Dependencias clave: `stock`, `sale_stock`.
	- Impacto: Cambia la estructura de datos del picking para adaptarse a procesos internos.

24) stock_picking_responsable
	- Funcionalidad: Agrega campo "Responsable" al picking que se completa al validar.
	- Dependencias clave: `stock`.
	- Impacto: Añade trazabilidad de quién valida el picking; útil para control interno.

25) stock_picking_sale_validation
	- Funcionalidad: Validaciones adicionales en entregas basadas en órdenes de venta; incluye assets JS para validación por barcode.
	- Dependencias clave: `stock`, `sale_stock`, `stock_barcode`.
	- Impacto: Refuerza controles en entregas comerciales y permite integridad entre picking y pedido de venta.

26) stock_reception_type
	- Funcionalidad: Añade un campo de tipo de recepción (ej. Garantía) en tipos de operación de inventario.
	- Dependencias clave: `stock`.
	- Impacto: Permite categorizar recepciones y adaptar procesos de recepción a necesidades (garantía, inspección, etc.).
