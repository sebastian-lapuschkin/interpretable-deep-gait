import sys
import time
import os
import numpy as np
import scipy
import modules
import model_io


def run_3layer_fcnn(X,Y,L,S,outputfolder='./tmp', n_hidden=512, overwrite=False):
    """
    X is a dictionary of DataName -> np.array , containing raw input data
    X is a dictionary of Targetname -> np.array , containing binary labels
    L is a dictionary of DataName -> channel labels
    S is a dictionary of TargetName -> prepared index splits
    """

    #prepare model output
    MODELNAME = '3LayerFCNN-{}'.format(n_hidden)
    #and output folder
    if not os.path.isdir(outputfolder):
        os.mkdir(outputfolder)
    #grab stdout to relay all prints to a log file
    STDOUT = sys.stdout
    LOG = open(outputfolder + '/log.txt', 'ab') #append (each model trained this day)

    #write out data and stuff used in this configuration. we just keep the same seed every time to ensure reproducibility
    scipy.io.savemat(outputfolder+'/data.mat', X)
    scipy.io.savemat(outputfolder+'/targets.mat', Y)
    scipy.io.savemat(outputfolder+'/labels.mat', L)
    scipy.io.savemat(outputfolder+'/splits.mat', S)


    #loop over all possible combinatinos of things
    for xname, x in X.iteritems():
        for yname, y in Y.iteritems(): #target name, i.e. pick a label in name and data
            targetSplits = S[yname]
            for i in xrange(len(targetSplits)): #the splits for this target
                #create output directory for this run
                modeldir = '{}/{}/{}/{}/part-{}'.format(outputfolder, yname, xname, MODELNAME, i)
                if not os.path.isdir(modeldir):
                    os.makedirs(modeldir)

                t_start = time.time()
                #set output log to capture all prints
                sys.stdout = open('{}/log.txt'.format(modeldir), 'wb')

                iTest = targetSplits[i] #get split for validation and testing
                iVal = targetSplits[(i+1)%len(targetSplits)]
                iTrain = []
                for j in [r % len(targetSplits) for r in range(i+2, (i+2)+(len(targetSplits)-2))]: #pool remaining data into training set.
                    iTrain.extend(targetSplits[j])

                #format the data for this run
                Xtrain = x[iTrain, ...]
                Ytrain = y[iTrain, ...]

                Xval = x[iVal, ...]
                Yval = y[iVal, ...]

                Xtest = x[iTest, ...]
                Ytest = y[iTest, ...]

                #get original data shapes
                Ntr, T, C = Xtrain.shape
                Nv = Xval.shape[0]
                Nte = Xtest.shape[0]

                #reshape for fully connected inputs
                Xtrain = np.reshape(Xtrain, [Ntr, -1])
                Xval = np.reshape(Xval, [Nv, -1])
                Xtest = np.reshape(Xtest, [Nte, -1])

                #input dims and output dims
                D = Xtrain.shape[1]
                L = Ytrain.shape[1]

                #create and train the model here
                nn = modules.Sequential([modules.Linear(D, n_hidden), modules.Rect(), modules.Linear(n_hidden,n_hidden), modules.Rect(), modules.Linear(n_hidden, L), modules.SoftMax()])
                nn.train(Xtrain, Ytrain, Xval=Xval, Yval=Yval, batchsize=5, lrate=0.005) # train the model
                nn.train(Xtrain, Ytrain, Xval=Xval, Yval=Yval, batchsize=5, lrate=0.001) # slower training once the model has converged somewhat
                nn.train(Xtrain, Ytrain, Xval=Xval, Yval=Yval, batchsize=5, lrate=0.0005)# one last epoch

                #test the model
                Ypred = nn.forward(Xtest)
                Rpred = nn.lrp(Ypred, lrp_var='epsilon', param=1e-5).reshape(Nte, T, C) #reshape data into original input shape
                RpredPresoftmax = nn.lrp(nn.modules[-1].Y, lrp_var='epsilon', param=1e-5).reshape(Nte, T, C)
                Ract = nn.lrp(Ytest, lrp_var='epsilon', param=1e-5).reshape(Nte, T, C)

                #measure test performance
                l1loss = np.abs(Ypred - Ytest).sum()/Nte
                predictions = np.argmax(Ypred, axis=1)
                groundTruth = np.argmax(Ytest, axis=1)
                acc = np.mean((predictions == groundTruth))

                t_end = time.time()

                #print results to terminal and log file
                message = '\n'
                message += '{} {}\n'.format(modeldir.replace('/', ' '),':')
                message += 'test accuracy: {}\n'.format(acc)
                message += 'test loss (l1): {}\n'.format(l1loss)
                message += 'train-test-sequence done after: {}s\n\n'.format(t_end-t_start)

                LOG.write(message)
                LOG.flush()
                STDOUT.write(message)

                #write out the model
                model_io.write(nn, '{}/model.txt'.format(modeldir))

                #write out performance
                with open('{}/scores.txt'.format(modeldir), 'wb') as f:
                    f.write('test loss (l1): {}\n'.format(l1loss))
                    f.write('test accuracy : {}'.format(acc))


                #write out matrices for prediction, GT heatmaps and prediction heatmaps
                scipy.io.savemat('{}/outputs.mat'.format(modeldir),
                                 {'Ypred': Ypred,
                                  'Rpred': Rpred,
                                  'RpredPresoftmax': RpredPresoftmax,
                                  'Ract': Ract,
                                  'l1loss': l1loss,
                                  'acc': acc})


                #reinstate original sys.stdout
                sys.stdout.close()
                sys.stdout = STDOUT

    LOG.close()