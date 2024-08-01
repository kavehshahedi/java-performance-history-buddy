docker stop jphb-container

docker rm -vf $(docker ps -aq)

docker build -t jphb .

docker run --name jphb-container -d jphb $1