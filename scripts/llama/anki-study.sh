#!/bin/bash
# Start Anki with AnkiConnect support
# Usage: anki-study.sh start|stop|status|install-addon

ACTION="${1:-start}"

case "$ACTION" in
    start)
        # Check if Anki is already running
        if pgrep -f "anki" > /dev/null; then
            echo "Anki ya está corriendo"
            # Test AnkiConnect
            curl -s http://localhost:8765 > /dev/null 2>&1
            if [ $? -eq 0 ]; then
                echo "AnkiConnect disponible en puerto 8765"
            else
                echo "AnkiConnect no disponible - instala el addon (código: 2055492159)"
            fi
            exit 0
        fi

        echo "Iniciando Anki..."
        flatpak --user run net.ankiweb.Anki &
        sleep 8

        # Test AnkiConnect
        curl -s http://localhost:8765 > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "AnkiConnect disponible en puerto 8765"
        else
            echo "Esperando a que AnkiConnect esté disponible..."
            for i in {1..10}; do
                sleep 2
                curl -s http://localhost:8765 > /dev/null 2>&1
                if [ $? -eq 0 ]; then
                    echo "AnkiConnect disponible en puerto 8765"
                    exit 0
                fi
            done
            echo "AnkiConnect no disponible"
            echo "Instala el addon manualmente: Tools > Add-ons > Get Add-ons > código: 2055492159"
        fi
        ;;
    stop)
        pkill -f "anki" 2>/dev/null
        echo "Anki detenido"
        ;;
    status)
        if pgrep -f "anki" > /dev/null; then
            echo "Anki: CORRIENDO"
            curl -s http://localhost:8765 > /dev/null 2>&1
            if [ $? -eq 0 ]; then
                echo "AnkiConnect: DISPONIBLE"
            else
                echo "AnkiConnect: NO DISPONIBLE (instalar addon 2055492159)"
            fi
        else
            echo "Anki: DETENIDO"
        fi
        ;;
    install-addon)
        echo "Para instalar AnkiConnect:"
        echo "1. Abre Anki"
        echo "2. Ve a Tools > Add-ons"
        echo "3. Click 'Get Add-ons...'"
        echo "4. Ingresa el código: 2055492159"
        echo "5. Reinicia Anki"
        ;;
    *)
        echo "Uso: $0 {start|stop|status|install-addon}"
        ;;
esac
