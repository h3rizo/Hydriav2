/**
 * Composable pour la gestion de la timezone Madagascar (UTC+3)
 * 
 * RÈGLES CRITIQUES (voir backend/TIMEZONE_GUIDE.md) :
 * - Import de dates: TOUJOURS utiliser localize() (PAS make_aware)
 * - Affichage de dates: TOUJOURS convertir avec astimezone() avant .date()
 * - Filtres par date: En JavaScript APRÈS conversion (JAMAIS parser new Date(string))
 * - Parser manuellement "YYYY-MM-DD" avec split()
 */

export const useTimezone = () => {
  const TIMEZONE = 'Indian/Antananarivo' // Madagascar UTC+3
  const UTC_OFFSET = 3 * 60 * 60 * 1000 // 3 heures en millisecondes

  /**
   * Parse une date au format "YYYY-MM-DD" en timezone Madagascar
   * NE PAS utiliser new Date(string) qui parse en UTC !
   */
  const parseDate = (dateString: string): Date | null => {
    if (!dateString) return null

    try {
      const parts = dateString.split('-')
      if (parts.length === 3) {
        const year = parseInt(parts[0])
        const month = parseInt(parts[1]) - 1 // Mois 0-indexé en JavaScript
        const day = parseInt(parts[2])

        // Créer la date en timezone locale (Madagascar)
        return new Date(year, month, day)
      }
    } catch (error) {
      console.error('Erreur parsing date:', error)
    }

    return null
  }

  /**
   * Formate une date au format dd/mm/yyyy
   */
  const formatDate = (date: Date | string | null): string => {
    if (!date) return ''

    const d = typeof date === 'string' ? parseDate(date) : date
    if (!d) return ''

    const day = String(d.getDate()).padStart(2, '0')
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const year = d.getFullYear()

    return `${day}/${month}/${year}`
  }

  /**
   * Formate une date au format yyyy-mm-dd (pour inputs HTML)
   */
  const formatDateISO = (date: Date | null): string => {
    if (!date) return ''

    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')

    return `${year}-${month}-${day}`
  }

  /**
   * Formate une datetime au format dd/mm/yyyy HH:mm
   */
  const formatDateTime = (date: Date | string | null): string => {
    if (!date) return ''

    const d = typeof date === 'string' ? new Date(date) : date
    if (!d || isNaN(d.getTime())) return ''

    const day = String(d.getDate()).padStart(2, '0')
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const year = d.getFullYear()
    const hours = String(d.getHours()).padStart(2, '0')
    const minutes = String(d.getMinutes()).padStart(2, '0')

    return `${day}/${month}/${year} ${hours}:${minutes}`
  }

  /**
   * Convertit une date UTC en date Madagascar
   */
  const utcToMadagascar = (utcDate: Date): Date => {
    return new Date(utcDate.getTime() + UTC_OFFSET)
  }

  /**
   * Convertit une date Madagascar en UTC
   */
  const madagascarToUTC = (localDate: Date): Date => {
    return new Date(localDate.getTime() - UTC_OFFSET)
  }

  /**
   * Obtient la date actuelle en timezone Madagascar
   */
  const now = (): Date => {
    return new Date()
  }

  /**
   * Obtient le début du jour en timezone Madagascar
   */
  const startOfDay = (date: Date = new Date()): Date => {
    const d = new Date(date)
    d.setHours(0, 0, 0, 0)
    return d
  }

  /**
   * Obtient la fin du jour en timezone Madagascar
   */
  const endOfDay = (date: Date = new Date()): Date => {
    const d = new Date(date)
    d.setHours(23, 59, 59, 999)
    return d
  }

  /**
   * Vérifie si une date est dans le mois spécifié
   */
  const isInMonth = (date: Date | string, year: number, month: number): boolean => {
    const d = typeof date === 'string' ? parseDate(date) : date
    if (!d) return false

    return d.getFullYear() === year && d.getMonth() === month - 1
  }

  /**
   * Obtient le nom du mois en français
   */
  const getMonthName = (monthIndex: number): string => {
    const months = [
      'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
      'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]
    return months[monthIndex] || ''
  }

  /**
   * Obtient le nombre de jours dans un mois
   */
  const getDaysInMonth = (year: number, month: number): number => {
    return new Date(year, month, 0).getDate()
  }

  return {
    TIMEZONE,
    UTC_OFFSET,
    parseDate,
    formatDate,
    formatDateISO,
    formatDateTime,
    utcToMadagascar,
    madagascarToUTC,
    now,
    startOfDay,
    endOfDay,
    isInMonth,
    getMonthName,
    getDaysInMonth,
  }
}
