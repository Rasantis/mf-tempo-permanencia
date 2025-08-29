================================================================================
	
	> MAIS FLUXO VEHICLE COUNTER
	> PIXFORCE
	_ Tutorial configuração da aplicação de contagem de veículos _
	
	Desenvolvedor: Rafael Santi 
	Cel.: (11)97765-5095
	
================================================================================

	Os arquivos de configuração, bem como o diretório para exportação do dado original (não formatado), deverá ser único para cada câmera.
	Os comandos abaixo deverão ser replicados para cada câmera. 
	Os parâmetros que são para informar a localização do arquivo de configuração deverá ser feito com o caminho absoluto. 
	Antes da primeira execuão, instalar a biblioteca de visão robótica. Abra o msdos, com permissões administrativas e execute o comando abaixo. 
	# pip install opencv-python
	
	
	**************************************************
	*** CONFIGURAÇÃO ***
	**************************************************
	
		> Arquivo de configuração de pontos de contagem:
			Local: C:\Users\maisfluxo\Desktop\executavel
			Exemplo de configuração: 
			{
				"codigocliente": 1724,
				"cameras": {
					"camera1": {
						"url": "rtsp://admin:mf6538dm@192.168.1.11:554/cam/realmonitor?channel=1&subtype=0",
						"faixas": {
							"faixa1": {
								"motorcycle": 26053,
								"car": 26052,
								"truck": 26051,
								"bus": 26054
							},
							"faixa2": {
								"motorcycle": 26058,
								"car": 26057,
								"truck": 26056,
								"bus": 26059
							}
						}
					}
				}
			}
			
		
		> Para começar, abra o msdos em modo administrador e entre no diretório C:\Users\maisfluxo\Desktop\executavel. Exemplo: 
			# cd C:\Users\maisfluxo\Desktop\executavel
		
		> Desenhar área de contagem (máximo 2 áreas por câmera):
			Para desenhar a área de contagem iremos executar o scripit desenho.py. 
			Parâmetros: 
			--source: fonte do arquivo de vídeo ou a URL do streaming da câmera.
			--output: onde o arquivo de configuração da área será salvo.
			
			# python desenho.py --source "<streaming rtsp ou localização do arquivo gravado>" --output "C:\Users\maisfluxo\Desktop\executavel\area\<camera>_area.json"
			
			Exemplo: 
			# python desenho.py --source "rtsp://admin:mf6538dm@192.168.1.11:554/cam/realmonitor?channel=1&subtype=0" --output ""C:\Users\maisfluxo\Desktop\executavel\area\camera1_area.json"
			
			Será carregado o frame do vídeo para que possamos desenhar a área de contagem. Esta área deverá ser um retângulo, de preferência com altura bem pequena.
			Deverá ser marcado os 4 pontos para delimitar a área, começando de cima para baixo, da esquerda para direita.
			Exemplo: 
				1	4
				2	3
				
			Ao terminar de delimitar a primeira área, pressione [r] para habilitar a delimitação de nova área. 
			Ao final, pressione [s] para salvar a configuração.


	**************************************************
	*** EXECUTAR APLICAÇÃO ***
	**************************************************
	
		> A execução da aplicação se dará por terminal, uma execução para cada câmera. 
			Criar um .bat para cada uma das câmeras e colocar na inicialização do servidor.
			Parâmetros: 
			--video_path: fonte do arquivo de vídeo ou a URL do streaming da câmera.
			--config path: localização do arquivo de configuração de pontos de contagem.
			--area_config_path: localização do arquivo de configuração de áreas (linhas de contagem).
			--output_dir: diretório onde serão salvos os arquivos de fluxo original (não formatado).
			--save_video: salvar o video gerado ou não (True or False). Prefêrencia sempre deixar este parâmetro com False.
		
		# yolo8.exe --video_path "<streaming rtsp ou localização do arquivo gravado>" --model_path "C:\Users\maisfluxo\Desktop\executavel\super_modelo.pt" --config_path "C:\Users\maisfluxo\Desktop\executavel\config\<camera>_config.json" --area_config_path "C:\Users\maisfluxo\Desktop\executavel\area\<camera>_area.json" --output_dir "C:\Users\maisfluxo\Desktop\executavel\txt_original\<camera>" --save_video False --video_interval 30
		
		Exemplo: 
		# yolo8.exe --video_path "rtsp://admin:mf6538dm@192.168.1.11:554/cam/realmonitor?channel=1&subtype=0" --model_path "C:\Users\maisfluxo\Desktop\executavel\super_modelo.pt" --config_path "C:\Users\maisfluxo\Desktop\executavel\config\camera1_config.json" --area_config_path "C:\Users\maisfluxo\Desktop\executavel\area\camera1_area.json" --output_dir "C:\Users\maisfluxo\Desktop\executavel\txt_original\camera1" --save_video False --video_interval 30
		
		> A aplicação será executada de forma automática através de .bat
		Localização .bat: "C:\Users\maisfluxo\Desktop\executavel"
		Nome .bat: "mfvc_<camera>.bat"
		
		Abra o arquivo .bat e alterar os parâmetros <url> e <camera> (linhas 10 e 11).
		Exemplo: "C:\Users\maisfluxo\Desktop\executavel\mfvc_camera1.bat"

			rem Parâmetros
			set url="rtsp://admin:mf6538dm@192.168.1.11:554/cam/realmonitor?channel=1&subtype=0"
			set camera=camera1
			title MaisFluxo_PixForce_VehicleCounter_%camera%
			cls

			rem Execução App
			cd C:\Users\maisfluxo\Desktop\executavel
			yolo8.exe --video_path %url% --config_path "C:\Users\maisfluxo\Desktop\executavel\config\%camera%_config.json" --area_config_path "C:\Users\maisfluxo\Desktop\executavel\area\%camera%_area.json" --output_dir "C:\Users\maisfluxo\Desktop\executavel\txt_original\%camera%" --save_video False

		> Após editar os arquivos .bat, adicionar os atalhos dos mesmos no diretório de inicialização do S.O.
		C:\Users\maisfluxo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
		
		> Agendamos um .bat para matar a aplicação às 00h05min e startamos a aplicação às 00h06min, para que o valor acumulado de fluxo não fique para o dia seguinte.
		

	**************************************************
	*** EXPORTAÇÃO/CONSOLIDAÇÃO FLUXO ***
	**************************************************
	
		> A consolidação e exportação do dado no formato Mais Fluxo de dará por execução de comando via terminal (msdos) a cada 30min para cada camera. 
		Para exportar o dado vamos executar o script formatar.py.
		Parâmetros: 
		--config_path: localização do arquivo de configuração de pontos de contagem.
		--output_directory: diretório onde estão salvos os arquivos de fluxo original (não formatado).
		--formatted_directory: diretório onde serão salvos os arquivos consolidados e formatados no padrão Mais Fluxo. Padrão: C:\MaisFluxoLocal\RetornoTXT 
		# python formatar.py --config_path "C:\Users\maisfluxo\Desktop\executavel\config\<camera>_config.json" --output_directory "C:\Users\maisfluxo\Desktop\executavel\txt_original\<camera>" --formatted_directory "C:\MaisFluxoLocal\RetornoTXT"
		
		Exemplo: 
		# python formatar.py --config_path "C:\Users\maisfluxo\Desktop\executavel\config\camera1_config.json" --output_directory "C:\Users\maisfluxo\Desktop\executavel\txt_original\camera1" --formatted_directory "C:\MaisFluxoLocal\RetornoTXT"
		
		> Agendamos a execução do script a cada 30min. 
		
		
	**************************************************
	*** SQLITE - IMPORTARÇÃO/EXPORTAÇÃO FLUXO ***
	**************************************************
	
		> A importação do dado em banco de dados local, sqlite, se dará por execução de comando via terminal (msdos) a cada 30min. 
		Para exportar o dado vamos executar o script db.py.
		Parâmetros: 
		--pasta: localização dos arquivos de fluxo já exportados no formato MaisFluxo (xml). Por padrão C:\MaisFluxoLocal\Historico.
		--banco: localização do arquivo de banco de dados sqlite (.db).
		
		# python.exe db.py --pasta "<diretorio_arquivos>" --banco "<arquivo_banco_de_dados.db>"
		
		Exemplo: 
		# python.exe db.py --pasta "C:\MaisFluxoLocal\Historico" --banco "C:\Users\maisfluxo\Desktop\executavel\sqlite\txt_historico.db"
		
		> A exportação do dado do banco de dados local, sqlite, se dará por execução de app a cada 30min. 
		Para exportar o dado vamos executar o app sqlite\sqlite_exportar_txt.exe. O app lê arquivo de configuração config.json onde é informado os seguintes dados:
		"codigo_empresa": código da empresa que será exportado o fluxo;
		"qtd_dias_fluxo": quantidade de dias que serão exportados do banco de dados. Valor 0 exportará o dia atual;
		"dir_original": diretório onde será gerado o arquivo original, sem o hash;
		"dir_txt": direrório onde ficará o arquivo gerado já com o hash; e
		"sqlite_db": nome do arquivo de banco de dados.
		
		Exemplo: 
		{
		  "codigo_empresa": 1731,
		  "qtd_dias_fluxo": 1,
		  "dir_original": ".",
		  "dir_txt": "C:\\MaisFluxoLocal\\RetornoTXT",
		  "sqlite_db": "txt_historico.db"
		}
		
		> Agendamos a execução do script de importação e do app de exportação cada 30min. 
				
		
	*** OBSERVAÇÕES ***
		A ideia inicial: No pior cenário são 8 cameras considerando que cada script irá conseguir lidar com 2 faixas cada.
		vamos rodar 4 scripts do tipo do yolo8.exe, cada um em um terminal com sua respectiva configuração de parâmetro, configurações, area de salvamento e etc.