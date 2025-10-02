#!/bin/bash

# フェリー空室確認システム デプロイスクリプト

set -e

# 設定
AWS_REGION="us-east-1"  # SES用にus-east-1を推奨
STACK_NAME="ferry-availability-checker"
ECR_REPO_NAME="ferry-availability-checker"

echo "=== フェリー空室確認システム デプロイ開始 ==="

# AWSアカウントIDを取得
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: $AWS_ACCOUNT_ID"

# ECRリポジトリのURIを構築
ECR_REPO_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"
echo "ECR Repository URI: $ECR_REPO_URI"

# まずECRリポジトリのみを作成するテンプレートでデプロイ
echo "--- ECRリポジトリを作成中 ---"
cat > ecr-template.yaml << EOF
AWSTemplateFormatVersion: '2010-09-09'
Description: 'ECR Repository for Ferry Availability Checker'

Resources:
  ECRRepository:
    Type: AWS::ECR::Repository
    Properties:
      RepositoryName: ferry-availability-checker
      ImageScanningConfiguration:
        ScanOnPush: true
      LifecyclePolicy:
        LifecyclePolicyText: |
          {
            "rules": [
              {
                "rulePriority": 1,
                "description": "Keep last 5 images",
                "selection": {
                  "tagStatus": "any",
                  "countType": "imageCountMoreThan",
                  "countNumber": 5
                },
                "action": {
                  "type": "expire"
                }
              }
            ]
          }

Outputs:
  ECRRepositoryURI:
    Description: "ECR Repository URI"
    Value: !GetAtt ECRRepository.RepositoryUri
EOF

# ECRリポジトリのみ先に作成
aws cloudformation deploy \
  --template-file ecr-template.yaml \
  --stack-name "${STACK_NAME}-ecr" \
  --region $AWS_REGION \
  --no-fail-on-empty-changeset

# ECRにログイン
echo "--- ECRにログイン中 ---"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO_URI

# Dockerイメージをビルド（x86_64プラットフォーム指定、キャッシュ無効化）
echo "--- Dockerイメージをビルド中（x86_64プラットフォーム） ---"
docker build --platform linux/amd64 --no-cache -t $ECR_REPO_NAME .

# イメージにタグを付ける
echo "--- イメージにタグを付与中 ---"
docker tag $ECR_REPO_NAME:latest $ECR_REPO_URI:latest

# イメージをECRにプッシュ
echo "--- イメージをECRにプッシュ中 ---"
docker push $ECR_REPO_URI:latest

# AWS CLIを使ってLambda関数を直接作成/更新
echo "--- Lambda関数を作成/更新中 ---"

# Lambda関数が存在するかチェック
if aws lambda get-function --function-name ferry-availability-checker --region $AWS_REGION 2>/dev/null; then
    echo "Lambda関数が存在します。更新中..."
    
    # Lambda関数が Active 状態になるまで待機
    echo "Lambda関数の状態を確認中..."
    while true; do
        STATE=$(aws lambda get-function \
          --function-name ferry-availability-checker \
          --region $AWS_REGION \
          --query 'Configuration.State' \
          --output text)
        
        echo "現在の状態: $STATE"
        
        if [ "$STATE" = "Active" ]; then
            echo "✅ Lambda関数が更新可能な状態です"
            break
        fi
        
        echo "⏳ 10秒待機..."
        sleep 10
    done
    
    # コードを更新
    aws lambda update-function-code \
        --function-name ferry-availability-checker \
        --image-uri $ECR_REPO_URI:latest \
        --region $AWS_REGION
    
    # コード更新完了を待つ
    echo "コード更新完了を待機中..."
    while true; do
        UPDATE_STATUS=$(aws lambda get-function \
          --function-name ferry-availability-checker \
          --region $AWS_REGION \
          --query 'Configuration.LastUpdateStatus' \
          --output text)
        
        echo "更新状況: $UPDATE_STATUS"
        
        if [ "$UPDATE_STATUS" = "Successful" ]; then
            echo "✅ コード更新が完了しました"
            break
        elif [ "$UPDATE_STATUS" = "Failed" ]; then
            echo "❌ コード更新に失敗しました"
            exit 1
        fi
        
        echo "⏳ 15秒待機..."
        sleep 15
    done
    
    # 環境変数を更新
    aws lambda update-function-configuration \
        --function-name ferry-availability-checker \
        --environment Variables="{DEPARTURE_DATE=20250809,NOTIFICATION_EMAIL=yuichiro.ebihara@gmail.com}" \
        --timeout 900 \
        --memory-size 2048 \
        --region $AWS_REGION
else
    echo "Lambda関数を新規作成中..."
    # IAMロールを作成
    aws iam create-role \
        --role-name ferry-availability-checker-role \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }' \
        --region $AWS_REGION 2>/dev/null || echo "ロールは既に存在します"
    
    # ポリシーをアタッチ
    aws iam attach-role-policy \
        --role-name ferry-availability-checker-role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
        --region $AWS_REGION 2>/dev/null || echo "ポリシーは既にアタッチされています"
    
    aws iam attach-role-policy \
        --role-name ferry-availability-checker-role \
        --policy-arn arn:aws:iam::aws:policy/AmazonSESFullAccess \
        --region $AWS_REGION 2>/dev/null || echo "SESポリシーは既にアタッチされています"
    
    # 少し待つ（ロールの作成完了を待つ）
    sleep 10
    
    # Lambda関数を作成
    aws lambda create-function \
        --function-name ferry-availability-checker \
        --role arn:aws:iam::$AWS_ACCOUNT_ID:role/ferry-availability-checker-role \
        --code ImageUri=$ECR_REPO_URI:latest \
        --package-type Image \
        --environment Variables="{DEPARTURE_DATE=20250809,NOTIFICATION_EMAIL=yuichiro.ebihara@gmail.com}" \
        --timeout 900 \
        --memory-size 2048 \
        --region $AWS_REGION
fi

# EventBridge（CloudWatch Events）でスケジュールを設定
echo "--- EventBridgeスケジュールを設定中 ---"

# Lambda関数に実行権限を付与
aws lambda add-permission \
    --function-name ferry-availability-checker \
    --statement-id allow-cloudwatch \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:$AWS_REGION:$AWS_ACCOUNT_ID:rule/ferry-availability-checker-schedule" \
    --region $AWS_REGION 2>/dev/null || echo "権限は既に設定されています"

# EventBridgeルールを作成
aws events put-rule \
    --name ferry-availability-checker-schedule \
    --schedule-expression "rate(1 hour)" \
    --description "Ferry availability checker hourly execution" \
    --region $AWS_REGION

# Lambda関数をターゲットとして設定
aws events put-targets \
    --rule ferry-availability-checker-schedule \
    --targets "Id"="1","Arn"="arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:ferry-availability-checker" \
    --region $AWS_REGION

echo "=== デプロイ完了 ==="
echo ""
echo "重要な設定項目:"
echo "1. Amazon SESでメール送信を有効にしてください"
echo "   - AWS Console > SES > Identity management > Email addresses"
echo "   - yuichiro.ebihara@gmail.com を追加して認証"
echo "   - 送信者アドレス（例: noreply@yourdomain.com）も認証が必要"
echo ""
echo "2. Lambda関数の設定確認:"
echo "   - 実行時間: 15分"
echo "   - メモリ: 2048MB"
echo "   - 環境変数: DEPARTURE_DATE=20250809"
echo ""
echo "3. スケジュール実行:"
echo "   - EventBridge（CloudWatch Events）で1時間おきに実行設定済み"
echo ""
echo "4. 手動テスト:"
echo "   aws lambda invoke --function-name ferry-availability-checker --region $AWS_REGION response.json"